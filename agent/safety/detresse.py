"""Filet de sécurité : expressions de détresse (arabe, darija, français).

Volontairement large : une fausse alerte vaut mieux qu'une détresse manquée.
Complété par le contrôle du modèle (classification.py), qui repère les formulations plus subtiles.
"""

import re

from rag.arabe import normaliser

EXPRESSIONS = [
    # arabe standard
    "لا اريد ان اعيش", "اريد ان اموت", "اقتل نفسي", "انتحر", "انتحار", "يضربني", "يضربونني", "يؤذيني",
    "خائف جدا", "خائفه جدا", "لا احد يحبني", "اكره حياتي", "حزين جدا", "حزينه جدا", "تحرش", "يلمسني",
    # darija
    "بغيت نموت", "ما بغيتش نعيش", "كيضربني", "كيضربوني", "خايف بزاف", "خايفه بزاف", "قتل راسي", "نقتل راسي",
    # français
    "envie de mourir", "me tuer", "me suicider", "suicide", "me frappe", "me frappent", "j'ai très peur",
    "personne ne m'aime", "je veux mourir", "me fait du mal", "me touche",
]
_NORMALISEES = [normaliser(e) for e in EXPRESSIONS]


def detecter(texte: str) -> bool:
    t = " " + re.sub(r"\s+", " ", normaliser(texte)) + " "
    return any(e in t for e in _NORMALISEES)
