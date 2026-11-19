"""Banque d'exercices du profil P2 (1AC, arabe), chargée depuis exercices_1ac.yaml.

Le fichier YAML est la seule source : le professeur peut le relire et le corriger directement.
Les explications des leçons viennent de docs/cours/ (outil lire_programme).
"""

from pathlib import Path

import yaml

FICHIER = Path(__file__).with_name("exercices_1ac.yaml")

_donnees = yaml.safe_load(FICHIER.read_text(encoding="utf-8"))
NOTIONS = {
    n["notion"]: {"niveau": _donnees["niveau"], "exercices": n["exercices"]} for n in _donnees["notions"]
}
EXERCICES = {ex["id"]: (notion, ex) for notion, d in NOTIONS.items() for ex in d["exercices"]}
