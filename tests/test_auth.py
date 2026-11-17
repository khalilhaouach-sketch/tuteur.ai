import sqlite3

from apps.api import db
from apps.api.auth import securite
from tests.conftest import inscrire


# --- Inscription et connexion du parent ---------------------------------------

def test_inscription_connecte_le_parent(client):
    inscrire(client)
    assert client.get("/parents/moi").json() == {"email": "parent@exemple.ma"}


def test_cookie_protege(client):
    r = inscrire(client)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_consentement_obligatoire(client):
    r = client.post(
        "/parents/inscription",
        json={"email": "a@exemple.ma", "mot_de_passe": "motdepasse123", "consentement": False},
    )
    assert r.status_code == 400
    assert client.post(
        "/parents/connexion", json={"email": "a@exemple.ma", "mot_de_passe": "motdepasse123"}
    ).status_code == 401


def test_consentement_date_enregistree(client):
    inscrire(client)
    conn = db.ouvrir()
    ligne = conn.execute("SELECT consentement_le, mot_de_passe_hash FROM parents").fetchone()
    assert ligne["consentement_le"]
    assert ligne["mot_de_passe_hash"].startswith("scrypt$")  # jamais en clair
    assert "motdepasse123" not in ligne["mot_de_passe_hash"]


def test_email_en_double_refuse(client):
    inscrire(client)
    r = client.post(
        "/parents/inscription",
        json={"email": "PARENT@exemple.ma", "mot_de_passe": "autremotdepasse", "consentement": True},
    )
    assert r.status_code == 409


def test_mot_de_passe_trop_court(client):
    r = client.post(
        "/parents/inscription",
        json={"email": "a@exemple.ma", "mot_de_passe": "court", "consentement": True},
    )
    assert r.status_code == 422


def test_email_invalide(client):
    r = client.post(
        "/parents/inscription",
        json={"email": "pas-un-email", "mot_de_passe": "motdepasse123", "consentement": True},
    )
    assert r.status_code == 422


def test_connexion_et_deconnexion(client):
    inscrire(client)
    client.post("/parents/deconnexion")
    assert client.get("/parents/moi").status_code == 401
    r = client.post(
        "/parents/connexion", json={"email": "Parent@Exemple.ma", "mot_de_passe": "motdepasse123"}
    )
    assert r.status_code == 200
    assert client.get("/parents/moi").status_code == 200


def test_mauvais_mot_de_passe(client):
    inscrire(client)
    client.post("/parents/deconnexion")
    r = client.post(
        "/parents/connexion", json={"email": "parent@exemple.ma", "mot_de_passe": "mauvais!!"}
    )
    assert r.status_code == 401
    assert client.get("/parents/moi").status_code == 401


def test_meme_message_si_email_inconnu(client):
    inscrire(client)
    a = client.post("/parents/connexion", json={"email": "parent@exemple.ma", "mot_de_passe": "x"})
    b = client.post("/parents/connexion", json={"email": "inconnu@exemple.ma", "mot_de_passe": "x"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_trop_d_essais_parent(client):
    inscrire(client)
    for _ in range(securite.MAX_ESSAIS_PARENT):
        client.post("/parents/connexion", json={"email": "parent@exemple.ma", "mot_de_passe": "x"})
    r = client.post(
        "/parents/connexion", json={"email": "parent@exemple.ma", "mot_de_passe": "motdepasse123"}
    )
    assert r.status_code == 429


# --- Gestion des élèves --------------------------------------------------------

def test_ajouter_et_lister_eleves(client):
    inscrire(client)
    r = client.post("/eleves", json={"prenom": "  Yasmine ", "profil": "P2"})
    assert r.status_code == 201
    client.post("/eleves", json={"prenom": "يوسف", "profil": "P1"})
    eleves = client.get("/eleves").json()
    assert [(e["prenom"], e["profil"]) for e in eleves] == [("Yasmine", "P2"), ("يوسف", "P1")]


def test_eleve_sans_donnees_superflues(client):
    inscrire(client)
    client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"})
    colonnes = {c[1] for c in db.ouvrir().execute("PRAGMA table_info(eleves)")}
    assert colonnes == {"id", "parent_id", "prenom", "profil", "cree_le"}


def test_profil_invalide(client):
    inscrire(client)
    assert client.post("/eleves", json={"prenom": "Yasmine", "profil": "P4"}).status_code == 422


def test_prenom_invalide(client):
    inscrire(client)
    for prenom in ["", "Yasmine 06 12 34 56 78", "a@b.ma", "x" * 31]:
        assert client.post("/eleves", json={"prenom": prenom, "profil": "P2"}).status_code == 422


def test_eleves_reserves_aux_parents_connectes(appareil_eleve):
    assert appareil_eleve.get("/eleves").status_code == 401
    assert appareil_eleve.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).status_code == 401


def test_limite_d_eleves(client):
    inscrire(client)
    for i in range(10):
        assert client.post("/eleves", json={"prenom": f"Enfant {'abcdefghij'[i]}", "profil": "P2"}).status_code == 201
    assert client.post("/eleves", json={"prenom": "Onzieme", "profil": "P2"}).status_code == 400


def test_un_parent_ne_voit_pas_les_eleves_d_un_autre(client, appareil_eleve):
    inscrire(client, "a@exemple.ma")
    eleve_a = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()

    autre = appareil_eleve  # second navigateur, pour un second parent
    inscrire(autre, "b@exemple.ma")
    assert autre.get("/eleves").json() == []
    assert autre.post(f"/eleves/{eleve_a['id']}/code").status_code == 404
    assert autre.delete(f"/eleves/{eleve_a['id']}").status_code == 404
    assert len(client.get("/eleves").json()) == 1


# --- Connexion de l'élève par code ---------------------------------------------

def _eleve_avec_code(client):
    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    return eleve, code


def test_parcours_complet(client, appareil_eleve):
    """Critère de la phase 1 : compte parent, sous-compte élève, connexion de l'élève."""
    eleve, code = _eleve_avec_code(client)
    assert len(code) == 6 and code.isdigit()

    r = appareil_eleve.post("/eleve/connexion", json={"code": code})
    assert r.status_code == 200
    assert r.json() == {"id": eleve["id"], "prenom": "Yasmine", "profil": "P2"}
    # L'appareil se souvient de l'élève.
    assert appareil_eleve.get("/eleve/moi").json()["prenom"] == "Yasmine"
    # L'élève n'a pas accès à l'espace parent.
    assert appareil_eleve.get("/eleves").status_code == 401


def test_code_a_usage_unique(client, appareil_eleve):
    _, code = _eleve_avec_code(client)
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 200
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 401


def test_nouveau_code_annule_l_ancien(client, appareil_eleve):
    eleve, ancien = _eleve_avec_code(client)
    nouveau = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    if ancien != nouveau:
        assert appareil_eleve.post("/eleve/connexion", json={"code": ancien}).status_code == 401
    assert appareil_eleve.post("/eleve/connexion", json={"code": nouveau}).status_code == 200


def test_code_expire(client, appareil_eleve):
    _, code = _eleve_avec_code(client)
    conn = db.ouvrir()
    conn.execute("UPDATE codes_acces SET expire_le = '2000-01-01T00:00:00+00:00'")
    conn.commit()
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 401


def test_code_au_mauvais_format(appareil_eleve):
    for code in ["12345", "1234567", "abcdef"]:
        assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 422


def test_trop_d_essais_de_code(client, appareil_eleve):
    _, code = _eleve_avec_code(client)
    faux = "000000" if code != "000000" else "111111"
    for _ in range(securite.MAX_ESSAIS_CODE):
        assert appareil_eleve.post("/eleve/connexion", json={"code": faux}).status_code == 401
    # Même le bon code est refusé tant que la limite est atteinte.
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 429


def test_supprimer_eleve_deconnecte_son_appareil(client, appareil_eleve):
    eleve, code = _eleve_avec_code(client)
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    assert client.delete(f"/eleves/{eleve['id']}").status_code == 204
    assert appareil_eleve.get("/eleve/moi").status_code == 401
    assert client.get("/eleves").json() == []


def test_seule_l_empreinte_du_code_et_du_jeton_est_stockee(client, appareil_eleve):
    _, code = _eleve_avec_code(client)
    conn = db.ouvrir()
    assert conn.execute("SELECT code_hash FROM codes_acces").fetchone()[0] != code
    appareil_eleve.post("/eleve/connexion", json={"code": code})
    jeton = appareil_eleve.cookies.get("session_eleve")
    stockes = [r[0] for r in conn.execute("SELECT jeton_hash FROM connexions")]
    assert jeton and jeton not in stockes


def test_schema_contient_les_tables_de_la_spec(client):
    tables = {r[0] for r in db.ouvrir().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"parents", "eleves", "notions", "tentatives", "maitrise", "seances", "rapports"} <= tables


def test_schema_refuse_une_autre_matiere_que_l_arabe(client):
    conn = db.ouvrir()
    try:
        conn.execute("INSERT INTO notions (matiere, niveau, intitule) VALUES ('francais', 'P2', 'x')")
        assert False, "une matière autre que l'arabe a été acceptée"
    except sqlite3.IntegrityError:
        pass
