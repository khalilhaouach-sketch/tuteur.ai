"""Phase 5 : mode CP (profil P1) : prompt, boutons de réponse, lettre suivante du programme."""

from agent.tools._commun import choix_de_l_enonce
from apps.api import db
from tests.conftest import inscrire
from tests.faux_claude import outil, reponse, texte


def _enfant_cp(client, appareil_eleve):
    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Adam", "profil": "P1"}).json()
    assert client.put(f"/eleves/{eleve['id']}/palier", json={"palier": 1}).status_code == 200
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 200
    return eleve


def test_choix_extraits_de_l_enonce():
    assert choix_de_l_enonce("مَا الحَرْفُ الأَوَّلُ فِي كَلِمَةِ «بَابٌ»؟ (تَ / ثَ / بَ)") == ["تَ", "ثَ", "بَ"]
    assert choix_de_l_enonce("ما وزن الفعل «جَلَسَ»؟") == []


def test_seance_cp_avec_boutons(client, appareil_eleve, faux_tuteur):
    _enfant_cp(client, appareil_eleve)
    faux = faux_tuteur([
        reponse(texte("مَرْحَبًا يَا آدَمُ! هَيَّا نَلْعَبُ مَعَ حَرْفِ البَاءِ.")),
        reponse(outil("generer_exercice", notion="حرف الباء", difficulte=1)),
        reponse(texte("مَا الحَرْفُ الأَوَّلُ فِي كَلِمَةِ «بَابٌ»؟")),
        reponse(outil("corriger", exercice_id="cp-02-1", reponse="تَ")),
        reponse(texte("اِسْمَعْ جَيِّدًا: بَ، بَابٌ. حَاوِلْ مَرَّةً أُخْرَى!")),
        reponse(outil("corriger", exercice_id="cp-02-1", reponse="بَ")),
        reponse(texte("أَحْسَنْتَ يَا آدَمُ! 🌟 مَا الحَرْفُ الأَوَّلُ فِي كَلِمَةِ «مَوْزٌ»؟")),
    ])
    r = appareil_eleve.post("/eleve/seances").json()
    assert r["profil"] == "P1" and r["choix"] == []
    # Le tuteur du CP utilise le prompt du CP, et la mémoire propose la première lettre du programme.
    assert "PROFIL : jeune enfant" in faux.appels[0]["system"]
    assert "Leçon suivante dans le parcours : حرف الميم" in faux.appels[0]["messages"][-1]["content"]

    s = r["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "نَعَمْ"}).json()
    assert r["choix"] == ["تَ", "ثَ", "بَ"]  # boutons de l'exercice
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "تَ"}).json()
    assert r["choix"] == ["تَ", "ثَ", "بَ"]  # deuxième essai : mêmes boutons
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "بَ"}).json()
    # Exercice réussi : boutons de l'exercice suivant du palier, donné par corriger (حرف الميم, non acquis).
    assert r["choix"] == ["مَ", "نَ", "بَ"]


def test_lettre_suivante_apres_une_lettre_acquise(client, appareil_eleve, faux_tuteur):
    eleve = _enfant_cp(client, appareil_eleve)
    conn = db.ouvrir()
    conn.execute("INSERT INTO notions (matiere, niveau, intitule) VALUES ('arabe', 'P1', 'حرف الميم')")
    conn.execute("INSERT INTO maitrise (eleve_id, notion_id, niveau) VALUES (?, last_insert_rowid(), 0.75)", (eleve["id"],))
    conn.commit()
    faux = faux_tuteur([reponse(texte("مَرْحَبًا"))])
    appareil_eleve.post("/eleve/seances")
    assert "Leçon suivante dans le parcours : حرف الباء" in faux.appels[0]["messages"][-1]["content"]


def test_seance_cp_limitee_a_20_minutes():
    from agent.safety.limites import DUREE_MAX_MINUTES

    assert DUREE_MAX_MINUTES["P1"] == 20


def test_page_eleve_a_un_mode_cp(client):
    page = client.get("/").text
    assert "mode-cp" in page and "choix" in page


def test_page_eleve_lit_a_voix_haute_au_cp(client):
    """La voix du téléphone (synthèse du navigateur) : lecture des messages et des choix au CP.
    Vérifiée aussi dans un vrai navigateur avec une voix simulée (voir le compte rendu de la phase 5)."""
    page = client.get("/").text
    for element in ["speechSynthesis", "texteAPrononcer", "boutonEcouter", 'id="test-voix"', '"ar-ma"', "u.rate = 0.8"]:
        assert element in page, element
    assert 'if (profil === "P1") parler(texte)' in page  # lecture automatique seulement au CP


def test_la_voix_ne_lit_pas_la_mise_en_forme(client):
    """Les astérisques du gras (**mot**), les # et les puces ne sont ni lus à voix haute ni affichés."""
    page = client.get("/").text
    assert 'replace(/[*_#`~|>=\\[\\]{}<•→←]/g, " ")' in page
    assert "afficherMisEnForme(div, texte)" in page
    assert "div.innerHTML" not in page  # le texte du modèle n'est jamais interprété comme du HTML
