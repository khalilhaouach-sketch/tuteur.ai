"""Phase 2 : agent tuteur P2, six outils, mémoire de l'élève, séance complète (API simulée)."""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import anthropic
import httpx

from agent import core
from agent.tools import DEFINITIONS, Contexte, executer
from agent.tools._commun import ErreurOutil, normaliser
from agent.tools.donnees_exemple import EXERCICES
from apps.api import db
from tests.faux_claude import outil, reponse, texte


# --- Séance complète, de l'accueil au bilan ------------------------------------

def test_seance_complete(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([
        # 1. Accueil
        reponse(texte("مرحبًا يا ياسمين! هل نبدأ بدرس إعراب الفعل المضارع؟")),
        # 2. L'élève accepte : rappel de la notion puis exercice
        reponse(outil("lire_programme", notion="إعراب الفعل المضارع")),
        reponse(outil("generer_exercice", notion="إعراب الفعل المضارع", difficulte=1)),
        reponse(texte("ما الحرف الذي نصب الفعل المضارع في الجملة: لَنْ يَتَأَخَّرَ التِّلْمِيذُ؟")),
        # 3. Réponse fausse : correction, indice
        reponse(outil("corriger", exercice_id="mudari3-1", reponse="التِّلْمِيذُ")),
        reponse(texte("ليس تمامًا. ما الحرف الذي جاء قبل الفعل؟")),
        # 4. Deuxième essai juste : progression puis révision
        reponse(outil("corriger", exercice_id="mudari3-1", reponse="لن")),
        reponse(outil("enregistrer_progression", exercice_id="mudari3-1")),
        reponse(outil("planifier_revision", notion="إعراب الفعل المضارع")),
        reponse(texte("أحسنت! الجواب صحيح.")),
        # 5. Fin de séance : récapitulatif
        reponse(texte("اليوم تعلمنا إعراب الفعل المضارع. أحسنت يا ياسمين!")),
    ])

    r = appareil_eleve.post("/eleve/seances")
    assert r.status_code == 201, r.text
    seance_id = r.json()["seance_id"]
    assert "ياسمين" in r.json()["reponse"]

    # La mémoire de l'élève est donnée à l'agent au début de la séance.
    ouverture = faux.appels[0]["messages"]
    assert ouverture[-1]["role"] == "system" and "Yasmine" in ouverture[-1]["content"]
    assert faux.appels[0]["system"] == Path("agent/profiles/college_1ac.md").read_text(encoding="utf-8")

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "نعم"})
    assert "لَنْ يَتَأَخَّرَ" in r.json()["reponse"]
    # Le rappel de la notion s'appuie sur le cours, avec sa référence.
    programme = json.loads(faux.derniers_resultats(2)[0]["content"])
    assert programme["passages"][0]["reference"].startswith("docs/cours/1ac_dawra1.md — إعراب الفعل المضارع")
    # L'exercice envoyé au modèle ne contient pas le corrigé.
    exercice_envoye = json.loads(faux.derniers_resultats()[0]["content"])
    assert exercice_envoye["exercice_id"] == "mudari3-1"
    assert "reponses" not in exercice_envoye and "التلميذ" not in json.dumps(exercice_envoye, ensure_ascii=False).replace("التِّلْمِيذُ", "")

    appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "التِّلْمِيذُ"})
    correction = json.loads(faux.derniers_resultats()[0]["content"])
    assert correction["verdict"] == "faux"
    assert correction["type_erreur"] == "خلط بين الناصب والفاعل"
    assert "indice" in correction and "bonne_reponse" not in correction

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "لن"})
    assert r.json()["reponse"] == "أحسنت! الجواب صحيح."

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/fin")
    assert r.status_code == 200
    assert faux.appels[-1]["tool_choice"] == {"type": "none"}  # pas de nouvel exercice à la fin

    # Tout est enregistré en base.
    conn = db.ouvrir()
    tentatives = conn.execute("SELECT reponse, verdict, type_erreur FROM tentatives ORDER BY id").fetchall()
    assert [tuple(t) for t in tentatives] == [
        ("التِّلْمِيذُ", "faux", "خلط بين الناصب والفاعل"),
        ("لن", "juste", None),
    ]
    maitrise = conn.execute("SELECT niveau, prochaine_revision FROM maitrise").fetchone()
    assert maitrise["niveau"] == 0.1  # réussi après une erreur
    assert maitrise["prochaine_revision"] == (date.today() + timedelta(days=1)).isoformat()
    seance = conn.execute("SELECT fin, journal, tokens_entree, tokens_sortie FROM seances").fetchone()
    assert seance["fin"] is not None
    assert seance["tokens_entree"] == 100 * 11 and seance["tokens_sortie"] == 20 * 11
    assert len(json.loads(seance["journal"])) > 10

    # Le bilan est arrivé chez le parent.
    bilans = client.get(f"/eleves/{eleve_connecte['id']}/rapports").json()
    assert len(bilans) == 1
    assert "Yasmine" in bilans[0]["texte"] and "إعراب الفعل المضارع : 1 exercice(s) réussi(s) sur 1" in bilans[0]["texte"]

    # La séance terminée n'accepte plus de messages.
    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "مرحبا"})
    assert r.status_code == 409


def test_memoire_entre_deux_seances(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([
        reponse(texte("مرحبًا")),
        reponse(outil("generer_exercice", notion="النكرة والمعرفة", difficulte=1)),
        reponse(texte("تمرين")),
        reponse(outil("corriger", exercice_id="nakira-1", reponse="معرفة")),
        reponse(texte("فكر مرة أخرى")),
        reponse(texte("إلى اللقاء")),
        reponse(texte("مرحبًا من جديد")),
    ])
    s1 = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s1}/messages", json={"texte": "تمرين"})
    appareil_eleve.post(f"/eleve/seances/{s1}/messages", json={"texte": "معرفة"})
    appareil_eleve.post(f"/eleve/seances/{s1}/fin")

    appareil_eleve.post("/eleve/seances")
    resume = faux.appels[-1]["messages"][-1]["content"]
    assert len(faux.appels[-1]["messages"]) == 2  # nouvelle séance : la conversation repart de zéro
    assert "Point faible le plus récent : النكرة والمعرفة (خلط بين النكرة والمعرفة)" in resume


# --- Robustesse de la boucle ---------------------------------------------------

def test_refus_n_abime_pas_le_journal(appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([
        reponse(texte("مرحبًا")),
        reponse(stop_reason="refusal"),
        reponse(texte("نعم، لنبدأ")),
    ])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "..."})
    assert r.json()["reponse"] == core.MESSAGE_REFUS
    journal = json.loads(db.ouvrir().execute("SELECT journal FROM seances").fetchone()[0])
    assert journal[-1]["role"] == "assistant"  # le tour refusé n'est pas enregistré
    assert appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "لنبدأ"}).status_code == 200


def test_api_indisponible(appareil_eleve, eleve_connecte, faux_tuteur):
    def panne(_):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    faux_tuteur([panne])
    r = appareil_eleve.post("/eleve/seances")
    assert r.status_code == 503
    assert db.ouvrir().execute("SELECT COUNT(*) FROM seances").fetchone()[0] == 0


def test_boucle_d_outils_limitee(appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([reponse(texte("مرحبًا"))] + [reponse(outil("lire_programme", notion="النكرة والمعرفة"))] * core.MAX_APPELS_PAR_TOUR)
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "?"})
    assert r.json()["reponse"] == core.MESSAGE_INDISPONIBLE


def test_erreur_d_outil_renvoyee_au_modele(appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([
        reponse(texte("مرحبًا")),
        reponse(outil("corriger", exercice_id="inexistant", reponse="x")),
        reponse(texte("لحظة")),
    ])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "x"})
    resultat = faux.derniers_resultats()[0]
    assert resultat["is_error"] is True and "exercice inconnu" in resultat["content"]


def test_message_trop_long(appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([reponse(texte("مرحبًا"))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "ا" * 1001})
    assert r.status_code == 422


def test_seance_reservee_a_son_eleve(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([reponse(texte("مرحبًا"))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    # Le parent (sans session élève) ne peut pas écrire dans la séance.
    assert client.post(f"/eleve/seances/{s}/messages", json={"texte": "x"}).status_code == 401
    assert appareil_eleve.post("/eleve/seances/999/messages", json={"texte": "x"}).status_code == 404


def test_prompt_cp_identique_a_spec():
    spec = Path("SPEC.md").read_text(encoding="utf-8")
    blocs = re.findall(r"```\n(.*?)```", spec, re.S)
    socle = next(b for b in blocs if b.startswith("Tu es un professeur"))
    p1 = next(b for b in blocs if "PROFIL : jeune enfant" in b).replace("[SOCLE COMMUN]\n\n", "")
    assert core.charger_prompt("P1") == socle.strip() + "\n\n" + p1.strip() + "\n"

def test_rapports_reserves_au_parent(client, appareil_eleve, eleve_connecte):
    from tests.conftest import inscrire

    client.post("/parents/deconnexion")
    inscrire(client, "autre@exemple.ma")
    assert client.get(f"/eleves/{eleve_connecte['id']}/rapports").status_code == 404


# --- Les outils ----------------------------------------------------------------

def test_exactement_six_outils_stricts_sans_choix_d_eleve():
    noms = [d["name"] for d in DEFINITIONS]
    assert noms == ["lire_programme", "generer_exercice", "corriger",
                    "enregistrer_progression", "planifier_revision", "rapport_parent"]
    for d in DEFINITIONS:
        assert d["strict"] is True and d["input_schema"]["additionalProperties"] is False
        # Le modèle ne choisit jamais l'élève : il vient de la séance.
        assert not any("eleve" in p for p in d["input_schema"]["properties"])


def test_prompt_p2_identique_a_spec():
    spec = Path("SPEC.md").read_text(encoding="utf-8")
    blocs = re.findall(r"```\n(.*?)```", spec, re.S)
    socle = next(b for b in blocs if b.startswith("Tu es un professeur"))
    p2 = next(b for b in blocs if "PROFIL : adolescent" in b).replace("[SOCLE COMMUN]\n\n", "")
    assert core.charger_prompt("P2") == socle.strip() + "\n\n" + p2.strip() + "\n"


def _ctx(eleve_id=1, seance_id=1):
    conn = db.ouvrir()
    return Contexte(db=conn, eleve_id=eleve_id, seance_id=seance_id, profil="P2")


def _preparer(client, faux_tuteur, appareil_eleve):
    faux_tuteur([reponse(texte("مرحبًا"))])
    return appareil_eleve.post("/eleve/seances").json()["seance_id"]


def test_correction_verifie_les_voyelles(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)

    def verdict(ex, rep):
        return executer(ctx, "corriger", {"exercice_id": ex, "reponse": rep})

    # Voyelles facultatives : absentes acceptées, mais une voyelle écrite doit être juste.
    assert verdict("mudari3-1", "لَنْ")["verdict"] == "juste"
    assert verdict("mudari3-2", " «الضمة». ")["verdict"] == "juste"
    faux = verdict("mudari3-3", "حَذْفِ النُّونِ")
    assert faux["verdict"] == "faux" and faux["type_erreur"] == "خطأ في الشكل (الحركات)"

    # Voyelles obligatoires (le وزن) : une voyelle fausse est une erreur...
    faux = verdict("mizan-1", "فَعِلَ")
    assert faux["verdict"] == "faux" and faux["type_erreur"] == "خطأ في الشكل (الحركات)"
    # ... et une réponse sans voyelles est redemandée, sans compter d'erreur.
    nb = ctx.db.execute("SELECT COUNT(*) FROM tentatives").fetchone()[0]
    assert verdict("mizan-2", "افعل")["verdict"] == "a_vocaliser"
    assert ctx.db.execute("SELECT COUNT(*) FROM tentatives").fetchone()[0] == nb
    # Hamza tolérée, soukoun et voyelle de l'alif de liaison facultatifs.
    assert verdict("mizan-2", "اَفْعَلَ")["verdict"] == "juste"
    assert verdict("mizan-3", "استَفعَلَ")["verdict"] == "juste"

    # Erreur de voyelle connue : le تنوين gardé avec «ال».
    tanwin = verdict("nakira-2", "الكِتَابٌ")
    assert tanwin["type_erreur"] == "إبقاء التنوين مع «ال» التعريف"
    assert verdict("nakira-2", "الكِتَابُ")["verdict"] == "juste"


def test_deuxieme_erreur_donne_l_explication(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    premier = executer(ctx, "corriger", {"exercice_id": "mizan-3", "reponse": "فعل"})
    assert premier["type_erreur"] == "إغفال الحروف الزائدة في الميزان" and "bonne_reponse" not in premier
    deuxieme = executer(ctx, "corriger", {"exercice_id": "mizan-3", "reponse": "لا أعرف"})
    assert deuxieme["exercice_termine"] and deuxieme["bonne_reponse"] == "اِسْتَفْعَلَ"
    assert executer(ctx, "enregistrer_progression", {"exercice_id": "mizan-3"})["niveau_maitrise"] == 0


def test_progression_exige_une_correction(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    for nom, entree in [("enregistrer_progression", {"exercice_id": "mudari3-2"}),
                        ("planifier_revision", {"notion": "إعراب الفعل المضارع"})]:
        try:
            executer(ctx, nom, entree)
            assert False
        except ErreurOutil:
            pass
    executer(ctx, "corriger", {"exercice_id": "mudari3-2", "reponse": "الفتحة"})
    try:  # un seul essai raté : l'exercice n'est pas terminé
        executer(ctx, "enregistrer_progression", {"exercice_id": "mudari3-2"})
        assert False
    except ErreurOutil:
        pass


def test_reussite_du_premier_coup_et_repetition_espacee(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    jours = []
    for ex in ["mudari3-1", "mudari3-2", "mudari3-3"]:
        executer(ctx, "corriger", {"exercice_id": ex, "reponse": EXERCICES[ex][1]["reponses"][0]})
        # corriger enregistre déjà : relire la progression ne compte pas le résultat une deuxième fois.
        executer(ctx, "enregistrer_progression", {"exercice_id": ex})
        executer(ctx, "enregistrer_progression", {"exercice_id": ex})
        jours.append(executer(ctx, "planifier_revision", {"notion": "إعراب الفعل المضارع"})["dans_jours"])
    assert jours == [3, 7, 14]  # maîtrise 0.3, 0.6, 0.9 : révisions de plus en plus espacées


def test_generer_exercice_adapte_et_sans_corrige(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    ex = executer(ctx, "generer_exercice", {"notion": "إعراب الفعل المضارع", "difficulte": 2})
    assert ex["exercice_id"] == "mudari3-2" and set(ex) == {"exercice_id", "notion", "difficulte", "enonce", "choix", "erreurs_recentes"}
    executer(ctx, "corriger", {"exercice_id": "mudari3-2", "reponse": "الفتحة"})
    executer(ctx, "corriger", {"exercice_id": "mudari3-2", "reponse": "الضمة"})
    suivant = executer(ctx, "generer_exercice", {"notion": "إعراب الفعل المضارع", "difficulte": 2})
    assert suivant["exercice_id"] != "mudari3-2"  # exercice réussi : pas reproposé
    assert suivant["erreurs_recentes"] == ["خلط بين علامة الرفع وعلامة النصب"]


def test_outils_limites_a_l_eleve_de_la_seance(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    executer(ctx, "corriger", {"exercice_id": "mudari3-1", "reponse": "التلميذ"})
    autre_id = ctx.db.execute(
        "INSERT INTO eleves (parent_id, prenom, profil, palier, cree_le) SELECT parent_id, 'Adam', 'P2', '1ac-4', cree_le"
        " FROM eleves WHERE id = ?", (eleve_connecte["id"],)).lastrowid
    autre = Contexte(db=ctx.db, eleve_id=autre_id, seance_id=s, profil="P2")
    assert executer(autre, "generer_exercice", {"notion": "إعراب الفعل المضارع", "difficulte": 1})["erreurs_recentes"] == []


def test_donnees_exemple_coherentes():
    from agent.tools._commun import a_des_voyelles, comparer

    for ex_id, (notion, ex) in EXERCICES.items():
        assert ex["reponses"] and ex["indice"] and ex["explication"], ex_id
        for r in ex["reponses"]:
            assert a_des_voyelles(r) or r == "آ", (ex_id, r)  # réponses de référence vocalisées (آ porte sa madda)
        for erreur in ex["erreurs"]:
            tolerer = ex.get("tolerer_hamza", True)
            assert all(comparer(erreur, r, False, tolerer) != "juste" for r in ex["reponses"]), (ex_id, erreur)


def test_banque_1ac_complete():
    from agent.tools.donnees_exemple import NOTIONS

    from agent import parcours

    # 28 lettres + 11 leçons de transition + 34 du primaire + 23 de 1AC, chacune dans un palier du parcours.
    assert len(NOTIONS) == 96
    assert sorted(n for p in parcours.PALIERS for n in p["notions"]) == sorted(NOTIONS)
    for notion, d in NOTIONS.items():
        assert {e["difficulte"] for e in d["exercices"]} == {1, 2, 3}, notion
        if d["niveau"] == "P1":  # lettres et transition : plus de 10 exercices par leçon
            assert len(d["exercices"]) > 10, notion


def test_chaque_exercice_se_corrige_comme_prevu(client, appareil_eleve, eleve_connecte, faux_tuteur):
    """Pour les 153 exercices (CP et 1AC) : la bonne réponse est juste, chaque erreur connue reçoit son type."""
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    for ex_id, (_, ex) in EXERCICES.items():
        for bonne in ex["reponses"]:
            assert executer(ctx, "corriger", {"exercice_id": ex_id, "reponse": bonne})["verdict"] == "juste", ex_id
        for erreur, type_erreur in ex["erreurs"].items():
            sortie = executer(ctx, "corriger", {"exercice_id": ex_id, "reponse": erreur})
            assert sortie["verdict"] in ("faux", "a_vocaliser"), (ex_id, erreur)
            if sortie["verdict"] == "faux":
                assert sortie["type_erreur"] == type_erreur, (ex_id, erreur)


def test_chadda_oubliee_est_une_erreur():
    from agent.tools._commun import comparer

    assert comparer("فَعَلَ", "فَعَّلَ", True) == "voyelles"  # lettre vocalisée, chadda oubliée
    assert comparer("فعل", "فَعَّلَ", True) == "a_vocaliser"  # aucune voyelle : on redemande


def test_exercices_limites_au_palier_de_l_eleve(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)  # au dernier palier : peut réviser les lettres du CP
    assert executer(ctx, "generer_exercice", {"notion": "حرف الباء", "difficulte": 1})["exercice_id"] == "cp-02-1"
    ctx.db.execute("UPDATE eleves SET palier = 'lettres-1' WHERE id = ?", (eleve_connecte["id"],))
    try:  # au palier 1 : pas de leçon d'un palier suivant
        executer(ctx, "generer_exercice", {"notion": "إعراب الفعل المضارع", "difficulte": 1})
        assert False, "une leçon d'un palier suivant a été proposée"
    except ErreurOutil as e:
        assert "palier 1" in str(e) and "حرف الميم" in str(e)


def test_cp_lettre_et_voyelle(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)

    def verdict(ex, rep):
        return executer(ctx, "corriger", {"exercice_id": ex, "reponse": rep})

    assert verdict("cp-02-1", "ب")["verdict"] == "juste"           # la lettre seule suffit
    assert verdict("cp-02-1", "بِ")["verdict"] == "faux"           # mais une voyelle écrite doit être la bonne
    assert verdict("cp-02-1", "تَ")["type_erreur"] == "خلط بين «ب» و«ت»"
    assert verdict("cp-02-3", "بُو")["verdict"] == "juste"
    assert verdict("cp-02-3", "بِي")["type_erreur"] == "خلط بين حروف المد"


def test_orthographe_de_la_hamza_stricte(client, appareil_eleve, eleve_connecte, faux_tuteur):
    """Au palier d'orthographe, « ا » à la place de « أ » est une faute ; ailleurs, la hamza reste tolérée."""
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)

    def verdict(ex, rep):
        return executer(ctx, "corriger", {"exercice_id": ex, "reponse": rep})["verdict"]

    assert verdict("hamzawst-3", "يَسْأَلُ") == "juste"
    assert verdict("hamzawst-3", "يسال") == "faux"         # hamza oubliée : faute d'orthographe
    assert verdict("wasl-3", "إِنْطِلَاقٌ") == "faux"       # hamza de liaison écrite comme hamza de coupure
    assert verdict("wasl-3", "انطلاق") == "juste"
    assert verdict("mizan-2", "اَفْعَلَ") == "juste"        # hors orthographe : hamza tolérée


def test_lecon_acquise_enchaine_sur_la_suivante(client, appareil_eleve, eleve_connecte, faux_tuteur):
    """corriger enregistre, planifie et donne l'exercice suivant du palier : deux réussites du premier coup
    suffisent pour «حرف الميم», puis la séance continue avec «حرف الباء» (un seul appel d'outil par réponse)."""
    from agent import parcours
    from agent.tools._commun import choix_de_l_enonce

    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    parcours.fixer_palier(ctx.db, eleve_connecte["id"], 1)
    premier = executer(ctx, "corriger", {"exercice_id": "cp-01-1", "reponse": "مَ"})
    assert premier["lecon_acquise"] is False and premier["exercice_suivant"]["exercice_id"] == "cp-01-4"
    assert premier["exercice_suivant"]["choix"] == choix_de_l_enonce(EXERCICES["cp-01-4"][1]["enonce"])
    deuxieme = executer(ctx, "corriger", {"exercice_id": "cp-01-4", "reponse": "مَ"})
    assert deuxieme["lecon_acquise"] is True and deuxieme["niveau_maitrise"] == 0.6
    assert deuxieme["exercice_suivant"]["notion"] == "حرف الباء"
    # La révision est planifiée sans appel d'outil supplémentaire.
    assert ctx.db.execute("SELECT COUNT(*) FROM maitrise WHERE prochaine_revision IS NOT NULL").fetchone()[0] == 1


def test_palier_termine_propose_le_test_de_passage(client, appareil_eleve, eleve_connecte, faux_tuteur):
    from agent import parcours
    from agent.tools._commun import notion_id

    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    parcours.fixer_palier(ctx.db, eleve_connecte["id"], 1)
    for n in parcours.palier(1)["notions"]:
        ctx.db.execute("INSERT INTO maitrise (eleve_id, notion_id, niveau) VALUES (?, ?, 0.9)",
                       (eleve_connecte["id"], notion_id(ctx.db, n)))
    resultat = executer(ctx, "corriger", {"exercice_id": "cp-01-1", "reponse": "مَ"})
    assert resultat["exercice_suivant"]["palier_termine"] is True


def test_prompts_enchainent_les_lecons_sans_annoncer_de_date():
    for profil in ("P1", "P2"):
        prompt = core.charger_prompt(profil)
        assert "sans appeler d'autre outil" in prompt
        assert "tu ne les annonces pas à l'élève" in prompt
        assert "Messages courts" in prompt
    assert "Un seul objectif par séance" not in core.charger_prompt("P1")


def test_effort_faible_au_cp():
    assert core.EFFORT == {"P1": "low", "P2": "medium"}


def test_cout_compte_le_cache():
    from types import SimpleNamespace

    from agent.cout import cout

    usage = SimpleNamespace(input_tokens=1000, cache_creation_input_tokens=4000,
                            cache_read_input_tokens=100_000, output_tokens=500)
    # 0,004 + 0,02 + 0,02 + 0,01 dollars
    assert round(cout(usage), 4) == 0.054
