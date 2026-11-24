"""Fichiers de mise en ligne (serveur + HTTPS)."""

from pathlib import Path

import yaml


def test_compose():
    c = yaml.safe_load(Path("compose.yml").read_text(encoding="utf-8"))
    tuteur, caddy = c["services"]["tuteur"], c["services"]["caddy"]
    assert "ports" not in tuteur                      # le tuteur n'est joignable que par Caddy
    assert caddy["ports"] == ["80:80", "443:443"]
    assert tuteur["environment"]["TUTEUR_COOKIE_SECURE"] == "1"
    assert "tuteur-data:/data" in tuteur["volumes"]   # données conservées entre les mises à jour


def test_image():
    d = Path("deploy/Dockerfile").read_text(encoding="utf-8")
    assert "--proxy-headers" in d                     # vraie IP du visiteur derrière Caddy
    assert "USER tuteur" in d                         # pas d'exécution en root
    assert "TUTEUR_DB=/data/tuteur.db" in d


def test_secrets_jamais_dans_l_image():
    ignores = Path(".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in ignores and "data" in ignores


def test_caddy_https():
    c = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    assert "{$DOMAINE}" in c and "reverse_proxy tuteur:8000" in c

