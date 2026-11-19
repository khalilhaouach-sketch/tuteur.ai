import pytest
from fastapi.testclient import TestClient

from apps.api.main import creer_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTEUR_DB", str(tmp_path / "test.db"))
    return creer_app()


@pytest.fixture
def client(app):
    """Navigateur du parent."""
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def appareil_eleve(app):
    """Un autre appareil (tablette de l'élève), sans les cookies du parent."""
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def inscrire(client, email="parent@exemple.ma", mot_de_passe="motdepasse123"):
    r = client.post(
        "/parents/inscription",
        json={"email": email, "mot_de_passe": mot_de_passe, "consentement": True},
    )
    assert r.status_code == 201, r.text
    return r


@pytest.fixture
def eleve_connecte(client, appareil_eleve):
    """Un parent, un élève P2 et l'appareil de l'élève déjà connecté."""
    inscrire(client)
    eleve = client.post("/eleves", json={"prenom": "Yasmine", "profil": "P2"}).json()
    code = client.post(f"/eleves/{eleve['id']}/code").json()["code"]
    assert appareil_eleve.post("/eleve/connexion", json={"code": code}).status_code == 200
    return eleve


@pytest.fixture
def faux_tuteur(app):
    """Remplace l'API Claude par un faux client ; renvoie une fonction pour fixer le script."""
    from agent.core import Tuteur
    from agent.safety.classification import mots_cles_seuls
    from apps.api.sessions.routes import get_tuteur
    from tests.faux_claude import FauxClient

    etat = {}

    def programmer(script):
        etat["client"] = FauxClient(script)
        app.dependency_overrides[get_tuteur] = lambda: Tuteur(etat["client"], classifieur=mots_cles_seuls)
        return etat["client"]

    yield programmer
    app.dependency_overrides.clear()
