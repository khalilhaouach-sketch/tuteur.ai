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


def _bonne(ex_id):
    from agent.tools.donnees_exemple import EXERCICES

    return EXERCICES[ex_id][1]["reponses"][0]


def _exercice_en_cours(seance_id):
    return db.ouvrir().execute("SELECT exercice_en_cours FROM seances WHERE id = ?", (seance_id,)).fetchone()[0]


def test_seance_cp_sans_ia(client, appareil_eleve, faux_tuteur):
    """Au CP, la séance est menée par le serveur : présentation de la leçon, exercice, indice, explication,
    félicitations, exercice suivant et récapitulatif, sans aucun appel à l'API."""
    _enfant_cp(client, appareil_eleve)
    faux = faux_tuteur([])
    r = appareil_eleve.post("/eleve/seances", json={"nombre": 3}).json()
    s = r["seance_id"]
    assert r["profil"] == "P1" and r["objectif"] == 3
    assert "مَرْحَبًا يَا Adam" in r["reponse"] and "دَرْسٌ جَدِيدٌ: حرف الميم" in r["reponse"]
    assert "مَوْزٌ، سَمَكٌ، قَلَمٌ" in r["reponse"]          # résumé du cours (docs/cours/cp_huruf.md)
    assert r["choix"] == ["مَ", "نَ", "بَ"]                  # premier exercice : cp-01-1

    # Première erreur : l'indice stocké, mêmes boutons.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "نَ"}).json()
    assert "اِسْمَعِ الصَّوْتَ الأَوَّلَ" in r["reponse"] and r["choix"] == ["مَ", "نَ", "بَ"]
    # « لَمْ أَفْهَمْ » après l'indice : l'explication stockée.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "لَمْ أَفْهَمْ"}).json()
    assert "حَرْفُ المِيمِ" in r["reponse"] and not r["terminee"]
    # Bonne réponse : félicitations et exercice suivant.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "مَ"}).json()
    assert r["choix"] and r["choix"] != ["مَ", "نَ", "بَ"] and not r["terminee"]
    for _ in range(2):
        r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": _bonne(_exercice_en_cours(s))}).json()
    # Trois exercices faits : récapitulatif et fin de séance, bilan pour le parent.
    assert r["terminee"] and "حرف الميم" in r["reponse"] and "3 / 3" in r["reponse"]
    assert db.ouvrir().execute("SELECT fin FROM seances WHERE id = ?", (s,)).fetchone()[0] is not None
    assert faux.appels == []
    # Le parent lit les échanges dans le journal, comme pour une séance avec l'IA.
    eleve_id = client.get("/eleves").json()[0]["id"]
    journal = client.get(f"/eleves/{eleve_id}/seances/{s}/journal").json()
    assert [e["qui"] for e in journal][:3] == ["tuteur", "eleve", "tuteur"]


def test_question_a_l_ia_puis_reponse_gardee(client, appareil_eleve, faux_tuteur):
    """Une question va à l'IA (sans outil) ; la même question sur le même exercice reçoit ensuite la réponse
    gardée, sans nouvel appel."""
    _enfant_cp(client, appareil_eleve)
    faux = faux_tuteur([reponse(texte("المِيمُ صَوْتُهُ «مْ». اِخْتَرِ الجَوَابَ."))])
    s = appareil_eleve.post("/eleve/seances", json={}).json()["seance_id"]
    question = {"texte": "كَيْفَ أَقْرَأُ هَذَا الحَرْفَ؟", "question": True}
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json=question).json()
    assert len(faux.appels) == 1 and "N'appelle aucun outil" in faux.appels[0]["messages"][-1]["content"]
    assert faux.appels[0]["tool_choice"] == {"type": "none"}
    assert "المِيمُ صَوْتُهُ" in r["reponse"] and r["choix"] == ["مَ", "نَ", "بَ"]  # l'exercice reste en cours
    assert db.ouvrir().execute("SELECT cout_dollars FROM seances WHERE id = ?", (s,)).fetchone()[0] > 0
    # Même question (sans voyelles cette fois) : réponse gardée, aucun appel.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "كيف أقرأ هذا الحرف", "question": True}).json()
    assert "المِيمُ صَوْتُهُ" in r["reponse"] and len(faux.appels) == 1


def test_grand_sans_ia_reponse_ecrite_et_securite(client, appareil_eleve, faux_tuteur):
    """Style « adolescent » (P2) : séance sans IA ; une réponse écrite est corrigée par le serveur ;
    un texte qui déclenche le contrôle de sécurité va à l'IA et alerte le parent."""
    from agent import parcours

    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()
    numero = parcours.numero_de("1ac-2")
    client.put(f"/eleves/{eleve['id']}/palier", json={"palier": numero})
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    faux = faux_tuteur([reponse(texte("أَنَا هُنَا لِأُسَاعِدَكَ. تَحَدَّثْ مَعَ وَالِدَيْكَ."))])
    r = appareil_eleve.post("/eleve/seances", json={"nombre": 5}).json()
    s = r["seance_id"]
    while r["choix"] == ["فَهِمْتُ، التَّالِي ←"]:  # étapes du cours d'abord
        r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "فَهِمْتُ، التَّالِي ←"}).json()
    ex_id = _exercice_en_cours(s)
    assert ex_id and faux.appels == []
    # Réponse écrite au clavier, corrigée sans IA.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": _bonne(ex_id)}).json()
    assert not r["terminee"] and faux.appels == []
    # Un message de détresse tapé à la place d'une réponse : l'IA répond, le parent est alerté.
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "أَنَا خَائِفٌ جِدًّا"}).json()
    assert len(faux.appels) == 1 and "تَحَدَّثْ مَعَ وَالِدَيْكَ" in r["reponse"]
    assert client.get(f"/eleves/{eleve['id']}/alertes").json()
    # Aucune réponse gardée pour un message de détresse.
    assert db.ouvrir().execute("SELECT COUNT(*) FROM reponses_ia").fetchone()[0] == 0


def test_nombre_d_exercices_regle_par_le_parent(client, appareil_eleve, faux_tuteur):
    eleve = _enfant_cp(client, appareil_eleve)
    assert client.put(f"/eleves/{eleve['id']}/reglages", json={"exercices_par_seance": 15}).status_code == 200
    assert client.put(f"/eleves/{eleve['id']}/reglages", json={"exercices_par_seance": 0}).status_code == 422
    assert appareil_eleve.get("/eleve/moi").json()["exercices_par_seance"] == 15
    faux_tuteur([])
    assert appareil_eleve.post("/eleve/seances", json={}).json()["objectif"] == 15        # réglage du parent
    assert appareil_eleve.post("/eleve/seances", json={"nombre": 5}).json()["objectif"] == 5  # choix de l'enfant


def test_lettre_suivante_apres_une_lettre_acquise(client, appareil_eleve, faux_tuteur):
    eleve = _enfant_cp(client, appareil_eleve)
    conn = db.ouvrir()
    conn.execute("INSERT INTO notions (matiere, niveau, intitule) VALUES ('arabe', 'P1', 'حرف الميم')")
    conn.execute("INSERT INTO maitrise (eleve_id, notion_id, niveau) VALUES (?, last_insert_rowid(), 0.75)", (eleve["id"],))
    conn.commit()
    faux_tuteur([])
    r = appareil_eleve.post("/eleve/seances").json()
    assert "دَرْسٌ جَدِيدٌ: حرف الباء" in r["reponse"]


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
    for element in ["speechSynthesis", "texteAPrononcer", "boutonEcouter", 'id="test-voix"', '"ar-ma"', "u.rate = vitesseVoix()", "vitesse-voix"]:
        assert element in page, element
    assert 'if (profil === "P1") parler(texte)' in page  # lecture automatique seulement au CP


def test_la_voix_ne_lit_pas_la_mise_en_forme(client):
    """Les astérisques du gras (**mot**), les # et les puces ne sont ni lus à voix haute ni affichés."""
    page = client.get("/").text
    assert "replace(/[*_#`~|>=\\[\\]{}<•→←✓✗]/g, \" \")" in page
    assert "afficherMisEnForme(div, texte)" in page
    assert "div.innerHTML" not in page  # le texte du modèle n'est jamais interprété comme du HTML


def test_seance_au_college(client, appareil_eleve, faux_tuteur):
    """Palier du collège (3AC) : présentation tirée de docs/cours/parcours_college.md et exercice à boutons."""
    from agent import parcours

    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()
    client.put(f"/eleves/{eleve['id']}/palier", json={"palier": parcours.numero_de("3ac-2")})
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    faux_tuteur([])
    r = appareil_eleve.post("/eleve/seances", json={"nombre": 5}).json()
    s = r["seance_id"]
    # Leçon découpée en petites étapes : la 1re, puis « فَهِمْتُ، التَّالِي » jusqu'au premier exercice.
    assert "دَرْسٌ جَدِيدٌ: أسلوب التعجب" in r["reponse"] and "(1/5)" in r["reponse"] and "مَا أَجْمَلَ السَّمَاءَ" in r["reponse"]
    assert r["choix"] == ["فَهِمْتُ، التَّالِي ←"]
    for n in range(2, 6):
        r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "فَهِمْتُ، التَّالِي ←"}).json()
        assert f"({n}/5)" in r["reponse"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "فَهِمْتُ، التَّالِي ←"}).json()
    assert "هَيَّا نَتَمَرَّنُ" in r["reponse"] and len(r["choix"]) >= 2
    # Aucune réponse n'a été comptée pendant les étapes.
    assert db.ouvrir().execute("SELECT COUNT(*) FROM tentatives").fetchone()[0] == 0


def test_page_eleve_choix_du_prenom_et_voix_pour_tous(client):
    page = client.get("/").text
    assert 'id="ecran-famille"' in page and "/famille/eleves" in page and 'id="changer"' in page
    # Le bouton 🔊 n'est plus réservé au CP ; la lecture automatique, si.
    assert "body.mode-cp .msg.tuteur .ecouter" not in page and 'if (profil === "P1") parler(texte)' in page


def test_pas_compris_pendant_une_etape_de_cours(client, appareil_eleve, faux_tuteur):
    """« لَمْ أَفْهَمْ » sur une étape du cours : l'IA réexplique l'étape, puis la leçon continue."""
    from agent import parcours

    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()
    client.put(f"/eleves/{eleve['id']}/palier", json={"palier": parcours.numero_de("3ac-2")})
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    faux = faux_tuteur([reponse(texte("حِينَ يُدْهِشُكَ شَيْءٌ تَقُولُ: مَا أَجْمَلَهُ!"))])
    s = appareil_eleve.post("/eleve/seances", json={"nombre": 5}).json()["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "لَمْ أَفْهَمْ"}).json()
    assert len(faux.appels) == 1 and "يُدْهِشُكَ" in r["reponse"]
    assert r["choix"] == ["فَهِمْتُ، التَّالِي ←"]  # on reste sur la même étape
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "فَهِمْتُ، التَّالِي ←"}).json()
    assert "(2/5)" in r["reponse"]



def test_lecture_a_voix_haute_soignee(client):
    """Lecture phrase par phrase, meilleure voix arabe (naturelle d'abord), choix de la voix, 🔊 pour arrêter."""
    page = client.get("/").text
    for element in ["function phrases", "function noteVoix", 'id="choix-voix"', "arreterLecture", "natural"]:
        assert element in page, element
