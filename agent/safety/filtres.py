"""Masque les données personnelles qu'un enfant pourrait taper (téléphone, e-mail, lien).

Appliqué avant tout envoi au modèle et avant tout enregistrement dans le journal.
"""

import re

MASQUE = "[معلومة محذوفة]"
_CHIFFRES = "0-9٠-٩۰-۹"  # chiffres latins, arabes et persans
_TELEPHONE = re.compile(rf"(?:\+|00)?[{_CHIFFRES}](?:[\s.\-]?[{_CHIFFRES}]){{7,}}")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_LIEN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def masquer(texte: str) -> tuple[str, bool]:
    """Renvoie le texte masqué et un indicateur « quelque chose a été masqué »."""
    masque = texte
    for motif in (_EMAIL, _LIEN, _TELEPHONE):
        masque = motif.sub(MASQUE, masque)
    return masque, masque != texte
