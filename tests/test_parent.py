"""Phase 4 : espace parent (tableau, progression, journal, bilans)."""

from tests.conftest import inscrire
from tests.faux_claude import outil, reponse, texte


def _seance_avec_exercice(appareil_eleve, faux_tuteur):
    faux_tuteur([
        reponse(texte("مرحبًا يا ياسمين")),
        reponse(outil("lire_programme", notion="إعراب الفعل المضارع")),
        reponse(outil("generer_exercice", notion="إعراب الفعل المضارع", difficulte=1)),
        reponse(texte("ما الحرف الذي نصب الفعل المضارع في الجملة: لَنْ يَتَأَخَّرَ التِّلْمِيذُ؟")),
        reponse(outil("corriger", exercice_id="mudari3-1", reponse="التلميذ")),
        reponse(texte("فكّر مرة أخرى.")),
        reponse(outil("corriger", exercice_id="mudari3-1", reponse="لن")),
        reponse(outil("enregistrer_progression", exercice_id="mudari3-1")),
        reponse(outil("planifier_revision", notion="إعراب الفعل المضارع")),
        reponse(texte("أحسنت!")),
        reponse(texte("إلى اللقاء")),
    ])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    for t in ["نعم", "التلميذ", "لن"]:
        appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": t})
    appareil_eleve.post(f"/eleve/seances/{s}/fin")
    return s


def test_parent_voit_progression_et_journal(client, appareil_eleve, eleve_connecte, faux_tuteur):
    """Critère de la phase 4 : un parent voit la progression et le journal."""
    s = _seance_avec_exercice(appareil_eleve, faux_tuteur)
    eid = eleve_connecte["id"]

    tableau = client.get("/parents/tableau").json()
    assert tableau[0]["prenom"] == "Yasmine" and tableau[0]["derniere_seance"]

    progression = client.get(f"/eleves/{eid}/progression").json()
    assert progression == [{
        "notion": "إعراب الفعل المضارع", "maitrise": 0.1, "prochaine_revision": progression[0]["prochaine_revision"],
        "exercices": 1, "reussis": 1, "erreur_frequente": "خلط بين الناصب والفاعل",
    }]

    seances = client.get(f"/eleves/{eid}/seances").json()
    assert seances[0]["id"] == s and seances[0]["fin_raison"] == "eleve"

    journal = client.get(f"/eleves/{eid}/seances/{s}/journal").json()
    qui = [m["qui"] for m in journal]
    assert qui[0] == "tuteur" and "eleve" in qui
    textes = [m["texte"] for m in journal]
    assert "التلميذ" in textes and "لن" in textes                     # ce que l'enfant a écrit
    assert any(t.startswith("sources : docs/cours/1ac_dawra1.md") for t in textes)  # le cours utilisé
    assert "verdict : faux (خلط بين الناصب والفاعل)" in textes and "verdict : juste" in textes
    assert not any("[L'élève" in t or "MÉMOIRE" in t for t in textes)  # rien de technique


def test_bilan_a_la_demande(client, appareil_eleve, eleve_connecte, faux_tuteur):
    _seance_avec_exercice(appareil_eleve, faux_tuteur)
    eid = eleve_connecte["id"]
    r = client.post(f"/eleves/{eid}/rapports?periode_jours=7")
    assert r.status_code == 201 and "sur les 7 derniers jours" in r.json()["texte"]
    assert len(client.get(f"/eleves/{eid}/rapports").json()) == 2  # bilan de fin de séance + celui-ci
    assert client.post(f"/eleves/{eid}/rapports?periode_jours=3").status_code == 400


def test_espace_parent_reserve_au_bon_parent(client, appareil_eleve, eleve_connecte, faux_tuteur):
    s = _seance_avec_exercice(appareil_eleve, faux_tuteur)
    eid = eleve_connecte["id"]
    # L'élève lui-même n'a pas accès à l'espace parent.
    for chemin in ["/parents/tableau", f"/eleves/{eid}/progression", f"/eleves/{eid}/seances/{s}/journal"]:
        assert appareil_eleve.get(chemin).status_code == 401
    # Un autre parent non plus.
    client.post("/parents/deconnexion")
    inscrire(client, "autre@exemple.ma")
    assert client.get("/parents/tableau").json() == []
    for chemin in [f"/eleves/{eid}/progression", f"/eleves/{eid}/seances", f"/eleves/{eid}/seances/{s}/journal",
                   f"/eleves/{eid}/alertes", f"/eleves/{eid}/rapports"]:
        assert client.get(chemin).status_code == 404, chemin


def test_pages_servies(client):
    assert "Espace parent" in client.get("/parent").text
    assert "Tuteur IA" in client.get("/").text


def test_connexion_utilisable_depuis_un_autre_fil(tmp_path, monkeypatch):
    """FastAPI peut fermer la connexion dans un autre fil d'exécution que celui qui l'a ouverte."""
    import threading

    from apps.api import db

    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "fil.db"))
    gen = db.get_db()
    conn = next(gen)
    erreurs = []

    def ailleurs():
        try:
            conn.execute("SELECT 1")
            gen.close()
        except Exception as e:  # noqa: BLE001
            erreurs.append(e)

    t = threading.Thread(target=ailleurs)
    t.start(); t.join()
    assert erreurs == []
