"""Phase 6 : parcours unique en paliers (positionnement, passage, confirmation du parent)."""

import json

from agent import parcours
from agent.tools.donnees_exemple import EXERCICES
from apps.api import db
from tests.conftest import inscrire
from tests.faux_claude import reponse, texte


def _enfant(client, appareil_eleve, profil="P1", palier=None):
    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Adam", "profil": profil}).json()
    if palier:
        client.put(f"/eleves/{eleve['id']}/palier", json={"palier": palier})
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    return eleve


def _exercice_en_cours(test_id):
    etat = json.loads(db.ouvrir().execute("SELECT etat FROM tests_palier WHERE id = ?", (test_id,)).fetchone()[0])
    return EXERCICES[etat["questions"][len(etat["reponses"])]][1]


def _repondre(appareil_eleve, test_id, juste):
    ex = _exercice_en_cours(test_id)
    rep = ex["reponses"][0] if juste else "جواب خاطئ"
    return appareil_eleve.post(f"/eleve/tests/{test_id}/reponses", json={"reponse": rep}).json()


def test_parcours_bien_forme():
    assert parcours.DERNIER == 14 and parcours.SEUIL_PASSAGE == 0.8
    assert [p["numero"] for p in parcours.PALIERS] == list(range(1, parcours.DERNIER + 1))
    assert parcours.palier_de("حرف الميم") == 1 and parcours.palier_de("المبني للمجهول") == parcours.DERNIER
    # Ordre : lettres, transition, primaire, 1AC.
    assert [p["id"] for p in parcours.PALIERS][5:11] == ["transition-3", "primaire-3ap", "primaire-4ap", "primaire-5ap-1", "primaire-5ap-2", "1ac-1"]
    assert parcours.notions_accessibles(1) == parcours.palier(1)["notions"]


def test_seance_impossible_avant_positionnement(client, appareil_eleve, faux_tuteur):
    _enfant(client, appareil_eleve)
    faux_tuteur([])
    r = appareil_eleve.post("/eleve/seances")
    assert r.status_code == 409 and "test" in r.json()["detail"]
    assert appareil_eleve.get("/eleve/moi").json()["palier"] is None


def test_positionnement_place_au_premier_palier_rate(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve)
    r = appareil_eleve.post("/eleve/tests", json={"type": "positionnement"}).json()
    tid = r["test_id"]
    assert r["question"]["palier"] == 1 and r["question"]["choix"]
    assert "reponses" not in r["question"]  # jamais le corrigé
    # Réussit les paliers 1 à 3, rate le palier 4.
    while True:
        palier = _exercice_en_cours(tid) and json.loads(
            db.ouvrir().execute("SELECT etat FROM tests_palier WHERE id = ?", (tid,)).fetchone()[0])["palier"]
        r = _repondre(appareil_eleve, tid, juste=palier <= 3)
        if r["resultat"]:
            break
    assert r["resultat"]["statut"] == "a_confirmer" and r["resultat"]["palier_propose"] == 4

    # Le parent voit le résultat et le confirme.
    suivi = client.get(f"/eleves/{eleve['id']}/parcours").json()
    assert suivi["palier"] is None and suivi["tests"][0]["statut"] == "a_confirmer"
    assert client.post(f"/eleves/{eleve['id']}/tests/{tid}/decision", json={"accepte": True}).json() == {"palier": 4}
    suivi = client.get(f"/eleves/{eleve['id']}/parcours").json()
    assert suivi["palier"] == 4
    assert [p["etat"] for p in suivi["paliers"][:5]] == ["valide", "valide", "valide", "actuel", "a_venir"]
    assert appareil_eleve.get("/eleve/moi").json()["titre_palier"] == "الحركات والمقاطع"


def test_positionnement_d_un_eleve_avance(client, appareil_eleve):
    _enfant(client, appareil_eleve, profil="P2")
    tid = appareil_eleve.post("/eleve/tests", json={"type": "positionnement"}).json()["test_id"]
    questions = 0
    while True:
        r = _repondre(appareil_eleve, tid, juste=True)
        questions += 1
        if r["resultat"]:
            break
    assert r["resultat"]["palier_propose"] == parcours.DERNIER
    assert questions == 3 * parcours.DERNIER  # 3 questions par palier


def test_passage_reussi_puis_confirme(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve, palier=4)
    r = appareil_eleve.post("/eleve/tests", json={"type": "passage"}).json()
    tid = r["test_id"]
    nb = len(parcours.palier(4)["notions"])  # une question par leçon du palier
    for i in range(nb):
        r = _repondre(appareil_eleve, tid, juste=True)
        assert r["verdict"] == "juste"
    assert r["resultat"] == {"statut": "a_confirmer", "palier_propose": 5, "score": 1.0,
                             "titre_palier": parcours.palier(5)["titre"]}
    client.post(f"/eleves/{eleve['id']}/tests/{tid}/decision", json={"accepte": True})
    assert appareil_eleve.get("/eleve/moi").json()["palier"] == 5


def test_passage_rate(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve, palier=4)
    tid = appareil_eleve.post("/eleve/tests", json={"type": "passage"}).json()["test_id"]
    for juste in [True, True, True, False]:  # 75 % < 80 %
        r = _repondre(appareil_eleve, tid, juste)
    assert r["resultat"]["statut"] == "echoue"
    assert client.post(f"/eleves/{eleve['id']}/tests/{tid}/decision", json={"accepte": True}).status_code == 409
    assert appareil_eleve.get("/eleve/moi").json()["palier"] == 4


def test_parent_peut_refuser(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve, palier=4)
    tid = appareil_eleve.post("/eleve/tests", json={"type": "passage"}).json()["test_id"]
    for _ in range(4):
        _repondre(appareil_eleve, tid, juste=True)
    assert client.post(f"/eleves/{eleve['id']}/tests/{tid}/decision", json={"accepte": False}).json() == {"palier": None}
    assert appareil_eleve.get("/eleve/moi").json()["palier"] == 4


def test_reponse_a_vocaliser_ne_compte_pas(client, appareil_eleve):
    _enfant(client, appareil_eleve, palier=1)
    conn = db.ouvrir()
    tid = appareil_eleve.post("/eleve/tests", json={"type": "passage"}).json()["test_id"]
    # Force une question à voyelles obligatoires (المد du CP) pour le premier exercice.
    etat = json.loads(conn.execute("SELECT etat FROM tests_palier WHERE id = ?", (tid,)).fetchone()[0])
    etat["questions"][0] = "cp-01-3"
    conn.execute("UPDATE tests_palier SET etat = ? WHERE id = ?", (json.dumps(etat, ensure_ascii=False), tid))
    conn.commit()
    r = appareil_eleve.post(f"/eleve/tests/{tid}/reponses", json={"reponse": "ما"}).json()
    assert r["verdict"] == "a_vocaliser" and r["question"]["numero"] == 1


def test_passage_impossible_sans_palier_ou_au_dernier(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve)
    assert appareil_eleve.post("/eleve/tests", json={"type": "passage"}).status_code == 409
    client.put(f"/eleves/{eleve['id']}/palier", json={"palier": parcours.DERNIER})
    assert appareil_eleve.post("/eleve/tests", json={"type": "passage"}).status_code == 409


def test_un_seul_test_en_cours(client, appareil_eleve):
    _enfant(client, appareil_eleve)
    t1 = appareil_eleve.post("/eleve/tests", json={"type": "positionnement"}).json()["test_id"]
    appareil_eleve.post("/eleve/tests", json={"type": "positionnement"})
    assert appareil_eleve.post(f"/eleve/tests/{t1}/reponses", json={"reponse": "x"}).status_code == 409


def test_parcours_reserve_au_bon_parent(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve, palier=2)
    client.post("/parents/deconnexion")
    inscrire(client, "autre@exemple.ma")
    assert client.get(f"/eleves/{eleve['id']}/parcours").status_code == 404
    assert client.put(f"/eleves/{eleve['id']}/palier", json={"palier": 9}).status_code == 404
    assert appareil_eleve.get("/parents/tableau").status_code == 401  # l'élève n'a pas accès


def test_palier_hors_parcours_refuse(client, appareil_eleve):
    eleve = _enfant(client, appareil_eleve)
    assert client.put(f"/eleves/{eleve['id']}/palier", json={"palier": parcours.DERNIER + 1}).status_code == 422


def test_memoire_donne_le_palier(client, appareil_eleve, faux_tuteur):
    _enfant(client, appareil_eleve, profil="P2", palier=parcours.palier_de("الميزان الصرفي"))
    faux = faux_tuteur([reponse(texte("مرحبًا"))])
    appareil_eleve.post("/eleve/seances")
    memoire = faux.appels[0]["messages"][-1]["content"]
    assert f"Palier actuel dans le parcours : 11/{parcours.DERNIER} « الصرف (1AC) »" in memoire
    # Les paliers précédents sont validés : on commence par la première leçon du palier 7.
    assert "Leçon suivante dans le parcours : الميزان الصرفي" in memoire


def test_pages_ont_le_parcours(client):
    assert "test-positionnement" in client.get("/").text
    assert "parcours" in client.get("/parent").text


def test_page_du_parcours_a_jour():
    """PARCOURS.md reprend bien agent/parcours.yaml."""
    from pathlib import Path

    texte = Path("PARCOURS.md").read_text(encoding="utf-8")
    for p in parcours.PALIERS:
        assert f"## Palier {p['numero']} : {p['titre']}" in texte
        assert "، ".join(p["notions"]) in texte


def test_paliers_enregistres_par_identifiant(client, appareil_eleve):
    """La base garde l'identifiant fixe du palier : insérer un palier ne déplace pas les enfants."""
    eleve = _enfant(client, appareil_eleve, palier=4)
    assert db.ouvrir().execute("SELECT palier FROM eleves WHERE id = ?", (eleve["id"],)).fetchone()[0] == "transition-1"
    assert appareil_eleve.get("/eleve/moi").json()["palier"] == 4


def test_anciennes_bases_converties(tmp_path, monkeypatch):
    """Une base de la première version (palier = numéro) est convertie au démarrage."""
    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "ancienne.db"))
    db.initialiser()
    conn = db.ouvrir()
    conn.execute("INSERT INTO parents (email, mot_de_passe_hash, consentement_le, cree_le) VALUES ('a@b.ma', 'x', 'd', 'd')")
    conn.execute("INSERT INTO eleves (parent_id, prenom, profil, palier, cree_le) VALUES (1, 'Sara', 'P1', 7, 'd')")
    conn.commit()
    db.initialiser()
    assert db.ouvrir().execute("SELECT palier FROM eleves").fetchone()[0] == "1ac-1"
