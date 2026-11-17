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
