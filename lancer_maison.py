"""Lance le tuteur pour la maison : les téléphones de la famille s'y connectent par le Wi-Fi.

    python lancer_maison.py

À utiliser seulement sur le Wi-Fi de la maison (protégé par mot de passe) : sans HTTPS, la
protection des cookies est désactivée (TUTEUR_COOKIE_SECURE=0). L'ordinateur doit rester
allumé pendant les séances. Pour un accès depuis partout, voir INSTALLATION.md (serveur en ligne).
"""

import os
import socket
import sys

PORT = int(os.environ.get("TUTEUR_PORT", "8000"))


def adresse_locale() -> str:
    """Adresse de l'ordinateur sur le Wi-Fi (aucune donnée n'est envoyée : on demande juste la route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def verifier() -> list[str]:
    problemes = []
    if sys.version_info < (3, 10):
        problemes.append(f"Python 3.10 ou plus récent est nécessaire (vous avez {sys.version.split()[0]}).")
    try:
        import anthropic, fastapi, uvicorn, yaml  # noqa: F401,E401
    except ImportError as e:
        problemes.append(f"Module manquant ({e.name}) : lancez d'abord « pip install -r requirements.txt ».")
    return problemes


def main() -> int:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    problemes = verifier()
    if problemes:
        print("\n".join("✗ " + p for p in problemes))
        return 1

    from apps.api.config import charger_env

    charger_env()
    os.environ["TUTEUR_COOKIE_SECURE"] = "0"  # pas de HTTPS sur le Wi-Fi de la maison
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✗ Clé API absente : copiez « .env.exemple » en « .env » et collez-y votre clé.")
        return 1

    ip = adresse_locale()
    print("\n  Tuteur IA démarré. Sur les téléphones connectés au même Wi-Fi, ouvrez :")
    print(f"    • Espace parent : http://{ip}:{PORT}/parent")
    print(f"    • Page élève    : http://{ip}:{PORT}/")
    print("  Laissez cette fenêtre ouverte pendant les séances. Ctrl+C pour arrêter.")
    print("  Si les téléphones n'arrivent pas à se connecter, autorisez Python dans le pare-feu.\n")

    import uvicorn

    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
