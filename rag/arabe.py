"""Normalisation de l'arabe pour la recherche (pas pour la correction des réponses)."""

import re

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_REMPLACEMENTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})
_MOT = re.compile(r"[\w]+", re.UNICODE)
# Préfixes retirés pour retrouver « الفاعل », « والفاعل », « فاعل » avec la même recherche.
_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
# Pronoms attachés en fin de mot, retirés aussi : « جزمه » -> « جزم ».
_SUFFIXES = ("هما", "كما", "هم", "هن", "كم", "كن", "ها", "نا", "ه", "ك")
MOTS_VIDES = {"في", "من", "على", "عن", "الى", "ما", "هو", "هي", "هل", "ان", "او", "ثم", "مع", "هذا", "هذه",
              "ذلك", "التي", "الذي", "كيف", "لماذا", "اشرح", "اريد", "لي", "عن"}


def normaliser(texte: str) -> str:
    return _TASHKEEL.sub("", texte).translate(_REMPLACEMENTS).lower()


def racine_legere(mot: str) -> str:
    for p in _PREFIXES:
        if mot.startswith(p) and len(mot) - len(p) >= 3:
            return mot[len(p):]
    return mot


def sans_suffixe(mot: str) -> str:
    for s in _SUFFIXES:
        if mot.endswith(s) and len(mot) - len(s) >= 3:
            return mot[: -len(s)]
    return mot


def formes(mot: str) -> set[str]:
    """Le mot, sans préfixe, et sans préfixe ni pronom final."""
    r = racine_legere(mot)
    return {mot, r, sans_suffixe(r)}


def mots(texte: str) -> list[str]:
    return _MOT.findall(normaliser(texte))


def texte_indexe(texte: str) -> str:
    """Chaque mot est indexé tel quel et sans préfixe."""
    sortie = []
    for m in mots(texte):
        sortie.append(m)
        sortie += sorted(formes(m) - {m})
    return " ".join(sortie)


def requete_fts(texte: str) -> str | None:
    """Requête FTS5 : un des mots (ou sa forme sans préfixe) suffit ; bm25 classe les passages."""
    termes = []
    for m in mots(texte):
        if m in MOTS_VIDES:
            continue
        termes.append("(" + " OR ".join(f'"{f}"' for f in sorted(formes(m))) + ")")
    return " OR ".join(termes) if termes else None
