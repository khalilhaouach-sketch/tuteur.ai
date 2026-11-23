"""Lecture du fichier .env (variables d'environnement locales, comme la clé API).

Le fichier .env reste sur l'ordinateur : il est exclu de Git (.gitignore).
Une variable déjà définie dans l'environnement n'est jamais remplacée.
"""

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def charger_env(fichier: Path | None = None) -> None:
    fichier = fichier or RACINE / ".env"
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        nom, valeur = ligne.split("=", 1)
        nom, valeur = nom.strip(), valeur.strip().strip('"').strip("'")
        if nom and nom not in os.environ:
            os.environ[nom] = valeur
