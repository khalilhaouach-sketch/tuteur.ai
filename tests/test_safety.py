"""Phase 4 : sécurité des séances (données personnelles, détresse, hors sujet, durée)."""

import json
from datetime import timedelta

import anthropic
import httpx

from agent.core import CONSIGNE_DETRESSE, CONSIGNE_DONNEES, CONSIGNE_HORS_SUJET, Tuteur
from agent.db_utils import iso, maintenant
from agent.safety import detresse, limites
from agent.safety.classification import Classifieur
from agent.safety.filtres import MASQUE, masquer
from apps.api import db
from apps.api.sessions.routes import get_tuteur
from tests.faux_claude import FauxClient, reponse, texte


# --- Données personnelles ------------------------------------------------------

def test_masque_telephones_emails_et_liens():
    for donnee in ["0612345678", "06 12 34 56 78", "+212 6 12 34 56 78", "٠٦١٢٣٤٥٦٧٨", "yasmine@exemple.ma", "www.exemple.ma"]:
        masque, trouve = masquer(f"رقمي {donnee} شكرا")
        assert trouve and donnee not in masque and MASQUE in masque, donnee


def test_ne_masque_pas_les_nombres_courts():
    assert masquer("قرأت 3 قصص سنة 2026") == ("قرأت 3 قصص سنة 2026", False)


def test_donnee_personnelle_jamais_envoyee_ni_enregistree(appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([reponse(texte("مرحبًا")), reponse(texte("لا تشارك رقم هاتفك. لنعد إلى الدرس."))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "هذا رقمي 0612345678"})
    envoye = json.dumps(faux.appels[-1]["messages"], ensure_ascii=False)
    assert "0612345678" not in envoye and CONSIGNE_DONNEES in envoye
    journal = db.ouvrir().execute("SELECT journal FROM seances").fetchone()[0]
    assert "0612345678" not in journal


# --- Détresse --------------------------------------------------------------------

def test_mots_cles_de_detresse():
    for message in ["أَنَا حَزِينٌ جِدًّا وَلَا أُرِيدُ أَنْ أَعِيشَ", "بابا كيضربني", "je veux mourir", "personne ne m'aime"]:
        assert detresse.detecter(message), message
    for message in ["ما هو الفاعل؟", "لا أعرف الجواب", "الحزن في القصيدة", "je ne sais pas"]:
        assert not detresse.detecter(message), message


def test_detresse_alerte_le_parent_et_guide_le_tuteur(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([reponse(texte("مرحبًا")), reponse(texte("أنا هنا معك. تكلم مع أمك أو أبيك الآن."))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "أنا خائف جدا، أبي يضربني"})
    assert faux.appels[-1]["messages"][-1] == {"role": "system", "content": CONSIGNE_DETRESSE}

    eid = eleve_connecte["id"]
    assert client.get("/parents/tableau").json()[0]["alertes"] == 1
    alerte = client.get(f"/eleves/{eid}/alertes").json()[0]
    assert alerte["extrait"] == "أنا خائف جدا، أبي يضربني" and alerte["seance_id"] == s
    assert client.post(f"/eleves/{eid}/alertes/{alerte['id']}/vue").status_code == 204
    assert client.get("/parents/tableau").json()[0]["alertes"] == 0


def test_alerte_gardee_meme_si_le_tuteur_tombe_en_panne(client, app, appareil_eleve, eleve_connecte, faux_tuteur):
    def panne(_):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    faux_tuteur([reponse(texte("مرحبًا")), panne])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "بغيت نموت"})
    assert r.status_code == 503
    assert len(client.get(f"/eleves/{eleve_connecte['id']}/alertes").json()) == 1


def test_classifieur_du_modele():
    faux = FauxClient([reponse(texte('{"detresse": true, "hors_sujet": false}'))])
    signaux = Classifieur(faux)("كل شيء مظلم ولا أحد يفهمني")  # aucun mot-clé : c'est le modèle qui repère
    assert signaux == {"detresse": True, "hors_sujet": False}
    appel = faux.appels[0]
    assert appel["output_config"]["format"]["type"] == "json_schema" and "tools" not in appel


def test_classifieur_hors_sujet():
    faux = FauxClient([reponse(texte('{"detresse": false, "hors_sujet": true}'))])
    assert Classifieur(faux)("من سيفوز بكأس العالم؟") == {"detresse": False, "hors_sujet": True}


def test_classifieur_en_panne_garde_les_mots_cles():
    def panne(_):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    assert Classifieur(FauxClient([panne]))("je veux mourir")["detresse"] is True
    assert Classifieur(FauxClient([reponse(stop_reason="refusal")]))("...")["detresse"] is True


def test_hors_sujet_recentre(app, appareil_eleve, eleve_connecte, faux_tuteur):
    faux = faux_tuteur([reponse(texte("مرحبًا")), reponse(texte("لنعد إلى درسنا."))])
    app.dependency_overrides[get_tuteur] = lambda: Tuteur(
        faux, classifieur=lambda t: {"detresse": False, "hors_sujet": True})
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "من سيفوز بكأس العالم؟"})
    assert faux.appels[-1]["messages"][-1] == {"role": "system", "content": CONSIGNE_HORS_SUJET}


# --- Durée des séances -----------------------------------------------------------

def _vieillir_seance(minutes):
    conn = db.ouvrir()
    conn.execute("UPDATE seances SET debut = ?", (iso(maintenant() - timedelta(minutes=minutes)),))
    conn.commit()


def test_temps_ecoule_puis_pause(client, appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([reponse(texte("مرحبًا")), reponse(texte("أحسنت اليوم!"))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    _vieillir_seance(limites.DUREE_MAX_MINUTES["P2"] + 1)

    r = appareil_eleve.post(f"/eleve/seances/{s}/messages", json={"texte": "سؤال"}).json()
    assert r["terminee"] is True and "أحسنت اليوم!" in r["reponse"]
    seance = client.get(f"/eleves/{eleve_connecte['id']}/seances").json()[0]
    assert seance["fin_raison"] == "temps"

    r = appareil_eleve.post("/eleve/seances")
    assert r.status_code == 429 and "pause" in r.json()["detail"]
    conn = db.ouvrir()
    conn.execute("UPDATE seances SET fin = ?", (iso(maintenant() - timedelta(minutes=limites.PAUSE_MINUTES)),))
    conn.commit()
    faux_tuteur([reponse(texte("مرحبًا من جديد"))])
    assert appareil_eleve.post("/eleve/seances").status_code == 201


def test_pas_de_pause_apres_une_fin_normale(appareil_eleve, eleve_connecte, faux_tuteur):
    faux_tuteur([reponse(texte("مرحبًا")), reponse(texte("إلى اللقاء")), reponse(texte("مرحبًا"))])
    s = appareil_eleve.post("/eleve/seances").json()["seance_id"]
    appareil_eleve.post(f"/eleve/seances/{s}/fin")
    assert appareil_eleve.post("/eleve/seances").status_code == 201


def test_durees_par_profil():
    debut = iso(maintenant() - timedelta(minutes=25))
    assert limites.temps_ecoule(debut, "P1") and not limites.temps_ecoule(debut, "P2")
