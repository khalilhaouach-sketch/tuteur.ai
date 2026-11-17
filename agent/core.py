"""Boucle de l'agent tuteur (API Claude + les six outils de agent/tools/, rien d'autre).

La conversation d'une séance est stockée dans seances.journal (format des messages de l'API),
et renvoyée telle quelle à chaque tour : on ne la modifie jamais, on ne fait qu'ajouter.
"""

import json
import sqlite3
from pathlib import Path

import anthropic

from agent import memoire
from agent.tools import DEFINITIONS, Contexte, ErreurOutil, executer

MODELE = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 8000
MAX_APPELS_PAR_TOUR = 12  # garde-fou contre une boucle d'outils sans fin
LONGUEUR_MAX_MESSAGE = 1000

PROFILS = {"P2": "college_2ac.md"}  # P3 en phase 5, P1 en phase 6
DOSSIER_PROFILS = Path(__file__).parent / "profiles"

MESSAGE_INDISPONIBLE = "عُذْرًا، حَدَثَ خَلَلٌ. حَاوِلْ مَرَّةً أُخْرَى بَعْدَ قَلِيلٍ."
MESSAGE_REFUS = "عُذْرًا، لَا أَسْتَطِيعُ الإِجَابَةَ عَنْ هَذَا. لِنَعُدْ إِلَى دَرْسِنَا."

OUVERTURE = "[L'élève ouvre une nouvelle séance.]"
CONSIGNE_FIN = (
    "La séance se termine. Donne à l'élève un récapitulatif très court de ce qu'il a travaillé "
    "et un encouragement. Ne propose pas de nouvel exercice."
)


class ProfilIndisponible(Exception):
    pass


class TuteurIndisponible(Exception):
    """L'API Claude n'a pas pu répondre (réseau, quota, clé absente...)."""


def charger_prompt(profil: str) -> str:
    if profil not in PROFILS:
        raise ProfilIndisponible(profil)
    return (DOSSIER_PROFILS / PROFILS[profil]).read_text(encoding="utf-8")


def _texte(contenu: list[dict]) -> str:
    return "\n".join(b["text"] for b in contenu if b.get("type") == "text").strip()


class Tuteur:
    def __init__(self, client):
        self.client = client  # anthropic.Anthropic() en production, un faux client dans les tests

    # --- API publique ---------------------------------------------------------

    def ouvrir_seance(self, db: sqlite3.Connection, eleve_id: int, seance_id: int) -> str:
        """Premier tour : l'agent reçoit le résumé de la mémoire de l'élève et l'accueille."""
        resume = memoire.resume(db, eleve_id)
        nouveaux = [
            {"role": "user", "content": OUVERTURE},
            {"role": "system", "content": resume},
        ]
        return self._tour(db, eleve_id, seance_id, nouveaux)

    def repondre(self, db: sqlite3.Connection, eleve_id: int, seance_id: int, texte: str) -> str:
        texte = texte.strip()[:LONGUEUR_MAX_MESSAGE]
        return self._tour(db, eleve_id, seance_id, [{"role": "user", "content": texte}])

    def conclure(self, db: sqlite3.Connection, eleve_id: int, seance_id: int) -> str:
        nouveaux = [
            {"role": "user", "content": "[L'élève termine la séance.]"},
            {"role": "system", "content": CONSIGNE_FIN},
        ]
        return self._tour(db, eleve_id, seance_id, nouveaux, outils=False)

    # --- Boucle -----------------------------------------------------------------

    def _tour(self, db, eleve_id, seance_id, nouveaux, outils=True) -> str:
        seance = db.execute(
            "SELECT s.journal, e.profil FROM seances s JOIN eleves e ON e.id = s.eleve_id"
            " WHERE s.id = ? AND s.eleve_id = ?",
            (seance_id, eleve_id),
        ).fetchone()
        systeme = charger_prompt(seance["profil"])
        historique = json.loads(seance["journal"])
        messages = historique + nouveaux
        ctx = Contexte(db=db, eleve_id=eleve_id, seance_id=seance_id, profil=seance["profil"])
        tokens_entree = tokens_sortie = 0
        texte = None

        for _ in range(MAX_APPELS_PAR_TOUR):
            reponse = self._appeler(systeme, messages, outils)
            tokens_entree += reponse.usage.input_tokens
            tokens_sortie += reponse.usage.output_tokens

            if reponse.stop_reason in ("refusal", "max_tokens"):
                # Réponse refusée ou tronquée : elle n'est pas ajoutée au journal.
                texte = MESSAGE_REFUS if reponse.stop_reason == "refusal" else MESSAGE_INDISPONIBLE
                break

            contenu = [b.model_dump(mode="json", exclude_none=True) for b in reponse.content]
            messages.append({"role": "assistant", "content": contenu})

            if reponse.stop_reason == "pause_turn":
                continue
            appels = [b for b in contenu if b["type"] == "tool_use"]
            if reponse.stop_reason != "tool_use" or not appels:
                texte = _texte(contenu) or MESSAGE_INDISPONIBLE
                break
            messages.append({"role": "user", "content": [self._outil(ctx, a) for a in appels]})

        if texte is None:
            texte = MESSAGE_INDISPONIBLE
        if len(messages) == len(historique) + len(nouveaux):
            # Aucune réponse de l'agent : on n'enregistre pas ce tour (un message « system »
            # sans réponse ne peut pas rester en fin de journal).
            messages = historique
        db.execute(
            "UPDATE seances SET journal = ?, tokens_entree = tokens_entree + ?,"
            " tokens_sortie = tokens_sortie + ? WHERE id = ?",
            (json.dumps(messages, ensure_ascii=False), tokens_entree, tokens_sortie, seance_id),
        )
        return texte

    def _appeler(self, systeme: str, messages: list, outils: bool):
        parametres = dict(
            model=MODELE,
            max_tokens=MAX_TOKENS,
            system=systeme,
            messages=messages,
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},
            # Si le modèle refuse pour une raison de sécurité, l'API réessaie sur un autre modèle.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            tools=DEFINITIONS,  # toujours la même liste, pour profiter du cache
        )
        if not outils:
            parametres["tool_choice"] = {"type": "none"}
        try:
            return self.client.beta.messages.create(**parametres)
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
            raise TuteurIndisponible(str(e)) from e

    @staticmethod
    def _outil(ctx: Contexte, appel: dict) -> dict:
        resultat = {"type": "tool_result", "tool_use_id": appel["id"]}
        try:
            sortie = executer(ctx, appel["name"], appel["input"])
            resultat["content"] = json.dumps(sortie, ensure_ascii=False)
        except ErreurOutil as e:
            resultat["content"] = str(e)
            resultat["is_error"] = True
        return resultat
