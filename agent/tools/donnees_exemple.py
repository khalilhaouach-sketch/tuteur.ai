"""Banques d'exercices, chargées depuis les fichiers YAML de ce dossier :
exercices_cp.yaml (profil P1, CP) et exercices_1ac.yaml (profil P2, 1AC).

Les fichiers YAML sont la seule source : le professeur peut les relire et les corriger directement.
Les explications des leçons viennent de docs/cours/ (outil lire_programme).
"""

from pathlib import Path

import yaml

FICHIERS = [Path(__file__).with_name(n) for n in ("exercices_cp.yaml", "exercices_1ac.yaml")]

NOTIONS: dict[str, dict] = {}
for _fichier in FICHIERS:
    _donnees = yaml.safe_load(_fichier.read_text(encoding="utf-8"))
    for _n in _donnees["notions"]:
        assert _n["notion"] not in NOTIONS, f"notion en double : {_n['notion']}"
        NOTIONS[_n["notion"]] = {"niveau": _donnees["niveau"], "exercices": _n["exercices"]}

EXERCICES = {ex["id"]: (notion, ex) for notion, d in NOTIONS.items() for ex in d["exercices"]}
