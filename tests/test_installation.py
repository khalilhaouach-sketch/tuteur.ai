"""Installation à la maison : fichier .env et lanceur."""

import os

from apps.api.config import charger_env


def test_charger_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# commentaire\nTUTEUR_TEST_A=valeur\nTUTEUR_TEST_B="entre guillemets"\nTUTEUR_TEST_C=deja\nligne sans egal\n',
                 encoding="utf-8")
    monkeypatch.setenv("TUTEUR_TEST_C", "existante")
    monkeypatch.delenv("TUTEUR_TEST_A", raising=False)
    monkeypatch.delenv("TUTEUR_TEST_B", raising=False)
    charger_env(f)
    assert os.environ["TUTEUR_TEST_A"] == "valeur"
    assert os.environ["TUTEUR_TEST_B"] == "entre guillemets"
    assert os.environ["TUTEUR_TEST_C"] == "existante"  # jamais remplacée
    for nom in ("TUTEUR_TEST_A", "TUTEUR_TEST_B"):
        monkeypatch.delenv(nom)


def test_env_absent_sans_erreur(tmp_path):
    charger_env(tmp_path / "inexistant")


def test_le_fichier_env_n_est_jamais_versionne():
    assert ".env" in open(".gitignore", encoding="utf-8").read().splitlines()


def test_lanceur():
    import lancer_maison

    ip = lancer_maison.adresse_locale()
    assert ip.count(".") == 3
    assert lancer_maison.verifier() == []
