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
        reponse(texte("مرحبًا يا ياسمين! هل نبدأ بدرس الفاعل؟")),
        # 2. L'élève accepte : rappel de la notion puis exercice
        reponse(outil("lire_programme", notion="الفاعل")),
        reponse(outil("generer_exercice", notion="الفاعل", difficulte=1)),
        reponse(texte("حَدِّدِ الفاعل في الجملة: كَتَبَ التِّلْمِيذُ الدَّرْسَ.")),
        # 3. Réponse fausse : correction, indice
        reponse(outil("corriger", exercice_id="fa3il-1", reponse="الدَّرْسَ")),
        reponse(texte("ليس تمامًا. مَنِ الذي كَتَبَ؟")),
        # 4. Deuxième essai juste : progression puis révision
        reponse(outil("corriger", exercice_id="fa3il-1", reponse="التلميذ")),
        reponse(outil("enregistrer_progression", exercice_id="fa3il-1")),
        reponse(outil("planifier_revision", notion="الفاعل")),
        reponse(texte("أحسنت! الجواب صحيح.")),
        # 5. Fin de séance : récapitulatif
        reponse(texte("اليوم تعلمنا الفاعل. أحسنت يا ياسمين!")),
    ])

    r = appareil_eleve.post("/eleve/seances")
    assert r.status_code == 201, r.text
    seance_id = r.json()["seance_id"]
    assert "ياسمين" in r.json()["reponse"]

    # La mémoire de l'élève est donnée à l'agent au début de la séance.
    ouverture = faux.appels[0]["messages"]
    assert ouverture[-1]["role"] == "system" and "Yasmine" in ouverture[-1]["content"]
    assert faux.appels[0]["system"] == Path("agent/profiles/college_2ac.md").read_text(encoding="utf-8")

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "نعم"})
    assert "كَتَبَ التِّلْمِيذُ" in r.json()["reponse"]
    # Le rappel de la notion s'appuie sur le cours, avec sa référence.
    programme = json.loads(faux.derniers_resultats(2)[0]["content"])
    assert programme["passages"][0]["reference"] == "docs/cours/2ac_exemples.md — الفاعل"
    # L'exercice envoyé au modèle ne contient pas le corrigé.
    exercice_envoye = json.loads(faux.derniers_resultats()[0]["content"])
    assert exercice_envoye["exercice_id"] == "fa3il-1"
    assert "reponses" not in exercice_envoye and "التلميذ" not in json.dumps(exercice_envoye, ensure_ascii=False).replace("التِّلْمِيذُ", "")

    appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "الدَّرْسَ"})
    correction = json.loads(faux.derniers_resultats()[0]["content"])
    assert correction["verdict"] == "faux"
    assert correction["type_erreur"] == "خلط بين الفاعل والمفعول به"
    assert "indice" in correction and "bonne_reponse" not in correction

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "التلميذ"})
    assert r.json()["reponse"] == "أحسنت! الجواب صحيح."

    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/fin")
    assert r.status_code == 200
    assert faux.appels[-1]["tool_choice"] == {"type": "none"}  # pas de nouvel exercice à la fin

    # Tout est enregistré en base.
    conn = db.ouvrir()
    tentatives = conn.execute("SELECT reponse, verdict, type_erreur FROM tentatives ORDER BY id").fetchall()
    assert [tuple(t) for t in tentatives] == [
        ("الدَّرْسَ", "faux", "خلط بين الفاعل والمفعول به"),
        ("التلميذ", "juste", None),
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
    assert "Yasmine" in bilans[0]["texte"] and "الفاعل : 1 exercice(s) réussi(s) sur 1" in bilans[0]["texte"]

    # La séance terminée n'accepte plus de messages.
    r = appareil_eleve.post(f"/eleve/seances/{seance_id}/messages", json={"texte": "مرحبا"})
    assert r.status_code == 409


def test_memoire_entre_deux_seances(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([
        reponse(texte("مرحبًا")),
        reponse(outil("generer_exercice", notion="المفعول به", difficulte=1)),
        reponse(texte("تمرين")),
        reponse(outil("corriger", exercice_id="maf3oul-1", reponse="أحمد")),
        reponse(texte("فكر مرة أخرى")),
        reponse(texte("إلى اللقاء")),
        reponse(texte("مرحبًا من جديد")),
    ])
    s1 = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s1}/messages", json={"texte": "تمرين"})
    appareil_eleve.post(f"/eleve/seances/{s1}/messages", json={"texte": "أحمد"})
    appareil_eleve.post(f"/eleve/seances/{s1}/fin")

    appareil_eleve.post("/eleve/seances")
    resume = faux.appels[-1]["messages"][-1]["content"]
    assert len(faux.appels[-1]["messages"]) == 2  # nouvelle séance : la conversation repart de zéro
    assert "Point faible le plus récent : المفعول به (خلط بين المفعول به والفاعل)" in resume


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
    faux_tuteur([reponse(texte("مرحبًا"))] + [reponse(outil("lire_programme", notion="الفاعل"))] * core.MAX_APPELS_PAR_TOUR)
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


def test_profil_pas_encore_disponible(client, appareil_eleve, faux_tuteur):
    from tests.conftest import inscrire

    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Adam", "profil": "P1"}).json()
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    faux_tuteur([])
    assert appareil_eleve.post("/eleve/seances").status_code == 400


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
    p2 = next(b for b in blocs if "2ᵉ année du collège. La matière" in b).replace("[SOCLE COMMUN]\n\n", "")
    assert core.charger_prompt("P2") == socle.strip() + "\n\n" + p2.strip() + "\n"


def _ctx(eleve_id=1, seance_id=1):
    conn = db.ouvrir()
    return Contexte(db=conn, eleve_id=eleve_id, seance_id=seance_id, profil="P2")


def _preparer(client, faux_tuteur, appareil_eleve):
    faux_tuteur([reponse(texte("مرحبًا"))])
    return appareil_eleve.post("/eleve/seances").json()["seance_id"]


def test_correction_tolere_voyelles_ponctuation_et_hamza(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    for reponse_eleve in ["التِّلْمِيذُ", " التلميذ. ", "«التلميذ»"]:
        assert executer(ctx, "corriger", {"exercice_id": "fa3il-1", "reponse": reponse_eleve})["verdict"] == "juste"
    assert executer(ctx, "corriger", {"exercice_id": "maf3oul-1", "reponse": "القصه"})["verdict"] == "faux"
    assert normaliser("أَحْمَدُ") == normaliser("احمد")


def test_deuxieme_erreur_donne_l_explication(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    premier = executer(ctx, "corriger", {"exercice_id": "kana-3", "reponse": "كان الطالب مجتهد"})
    assert premier["type_erreur"] == "نسيان نصب خبر كان" and "bonne_reponse" not in premier
    deuxieme = executer(ctx, "corriger", {"exercice_id": "kana-3", "reponse": "لا أعرف"})
    assert deuxieme["exercice_termine"] and deuxieme["bonne_reponse"] == "كان الطالب مجتهدا"
    assert executer(ctx, "enregistrer_progression", {"exercice_id": "kana-3"})["niveau_maitrise"] == 0


def test_progression_exige_une_correction(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    for nom, entree in [("enregistrer_progression", {"exercice_id": "fa3il-2"}),
                        ("planifier_revision", {"notion": "الفاعل"})]:
        try:
            executer(ctx, nom, entree)
            assert False
        except ErreurOutil:
            pass
    executer(ctx, "corriger", {"exercice_id": "fa3il-2", "reponse": "القمح"})
    try:  # un seul essai raté : l'exercice n'est pas terminé
        executer(ctx, "enregistrer_progression", {"exercice_id": "fa3il-2"})
        assert False
    except ErreurOutil:
        pass


def test_reussite_du_premier_coup_et_repetition_espacee(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    jours = []
    for ex in ["fa3il-1", "fa3il-2", "fa3il-3"]:
        executer(ctx, "corriger", {"exercice_id": ex, "reponse": EXERCICES[ex][1]["reponses"][0]})
        executer(ctx, "enregistrer_progression", {"exercice_id": ex})
        jours.append(executer(ctx, "planifier_revision", {"notion": "الفاعل"})["dans_jours"])
    assert jours == [1, 3, 7]  # maîtrise 0.25, 0.5, 0.75 : révisions de plus en plus espacées


def test_generer_exercice_adapte_et_sans_corrige(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    ex = executer(ctx, "generer_exercice", {"notion": "الفاعل", "difficulte": 2})
    assert ex["exercice_id"] == "fa3il-2" and set(ex) == {"exercice_id", "notion", "difficulte", "enonce", "erreurs_recentes"}
    executer(ctx, "corriger", {"exercice_id": "fa3il-2", "reponse": "القمح"})
    executer(ctx, "corriger", {"exercice_id": "fa3il-2", "reponse": "الفلاح"})
    suivant = executer(ctx, "generer_exercice", {"notion": "الفاعل", "difficulte": 2})
    assert suivant["exercice_id"] != "fa3il-2"  # exercice réussi : pas reproposé
    assert suivant["erreurs_recentes"] == ["خلط بين الفاعل والمفعول به"]


def test_outils_limites_a_l_eleve_de_la_seance(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _preparer(client, faux_tuteur, appareil_eleve)
    ctx = _ctx(eleve_connecte["id"], s)
    executer(ctx, "corriger", {"exercice_id": "fa3il-1", "reponse": "الدرس"})
    autre = Contexte(db=ctx.db, eleve_id=eleve_connecte["id"] + 1000, seance_id=s, profil="P2")
    assert executer(autre, "generer_exercice", {"notion": "الفاعل", "difficulte": 1})["erreurs_recentes"] == []


def test_donnees_exemple_coherentes():
    for ex_id, (notion, ex) in EXERCICES.items():
        assert ex["reponses"] and ex["indice"] and ex["explication"], ex_id
        bonnes = {normaliser(r) for r in ex["reponses"]}
        assert not bonnes & {normaliser(e) for e in ex["erreurs"]}, ex_id
