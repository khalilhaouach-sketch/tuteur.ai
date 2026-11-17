"""Faux client Claude : réponses écrites à l'avance, aucun appel réseau."""

import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


class Bloc:
    def __init__(self, **champs):
        self.__dict__.update(champs)

    def model_dump(self, mode="json", exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if not (exclude_none and v is None)}


def texte(t: str) -> Bloc:
    return Bloc(type="text", text=t)


def outil(nom: str, **entree) -> Bloc:
    return Bloc(type="tool_use", id=f"toolu_{next(_ids)}", name=nom, input=entree)


def reponse(*blocs: Bloc, stop_reason: str | None = None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end_turn"
    return SimpleNamespace(
        content=list(blocs),
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )


class FauxClient:
    """`script` : liste de réponses (ou de fonctions qui reçoivent les paramètres de l'appel)."""

    def __init__(self, script):
        self.script = list(script)
        self.appels: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **parametres):
        self.appels.append(copy.deepcopy(parametres))  # la liste de messages évolue ensuite
        if not self.script:
            raise AssertionError("le faux client n'a plus de réponse prévue")
        suivant = self.script.pop(0)
        return suivant(parametres) if callable(suivant) else suivant

    def derniers_resultats(self, n=-1) -> list[dict]:
        """Résultats d'outils envoyés au modèle lors de l'appel n."""
        dernier = self.appels[n]["messages"][-1]
        return [b for b in dernier["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
