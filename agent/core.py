"""Boucle de l'agent tuteur (API Claude + les six outils de agent/tools/, rien d'autre).

La conversation d'une séance est stockée dans seances.journal (format des messages de l'API),
et renvoyée telle quelle à chaque tour : on ne la modifie jamais, on ne fait qu'ajouter.
"""

import json
import logging
import sqlite3
from pathlib import Path

import anthropic

from agent import memoire
from agent.cout import cout
from agent.safety import filtres
from agent.safety.classification import Classifieur
from agent.db_utils import maintenant_iso
from agent.tools import DEFINITIONS, Contexte, ErreurOutil, executer

journal = logging.getLogger("tuteur")

MODELE = "claude-opus-5-5"
# Réflexion du modèle : faible au CP (exercices courts, corrigés par le serveur), moyenne pour les grands.
EFFORT = {"P1": "low", "P2": "medium"}
MAX_TOKENS = 8000
MAX_APPELS_PAR_TOUR = 12  # garde-fou contre une boucle d'outils sans fin
LONGUEUR_MAX_MESSAGE = 1000

PROFILS = {"P1": "cp_arabe.md", "P2": "college_1ac.md"}
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


CONSIGNE_DETRESSE = (
    "SIGNAL DE SÉCURITÉ : l'élève exprime peut-être une détresse, une peur ou un danger. Réponds avec douceur, "
    "sans faire de thérapie ni poser de questions intrusives. Encourage-le à en parler maintenant à un adulte de "
    "confiance (un parent, un enseignant). Tu peux lui dire qu'un adulte de sa famille sera prévenu. "
    "Ne reprends pas l'exercice dans cette réponse."
)
CONSIGNE_HORS_SUJET = (
    "Le dernier message de l'élève est hors sujet : ne réponds pas sur le fond, recentre-le gentiment "
    "et brièvement sur la leçon d'arabe."
)
CONSIGNE_DONNEES = (
    "L'élève a tapé une information personnelle, qui a été masquée. Rappelle-lui gentiment qu'il ne faut pas "
    "partager ce genre d'information, puis reviens à la leçon."
)


class Tuteur:
    def __init__(self, client, classifieur=None):
        self.client = client  # anthropic.Anthropic() en production, un faux client dans les tests
        # Contrôle de sécurité de chaque message de l'élève (détresse, hors sujet).
        self.classifieur = classifieur or Classifieur(client)

    # --- API publique ---------------------------------------------------------

    def ouvrir_seance(self, db: sqlite3.Connection, eleve_id: int, seance_id: int) -> str:
        """Premier tour : l'agent reçoit le résumé de la mémoire de l'élève et l'accueille."""
        resume = memoire.resume(db, eleve_id)
        nouveaux = [
            {"role": "user", "content": OUVERTURE},
            {"role": "system", "content": resume},
        ]
        return self._tour(db, eleve_id, seance_id, nouveaux)

    def repondre(self, db: sqlite3.Connection, eleve_id: int, seance_id: int, texte: str,
                 boutons: tuple[str, ...] = (), consigne: str | None = None, outils: bool = True) -> str:
        texte, masque = filtres.masquer(texte.strip()[:LONGUEUR_MAX_MESSAGE])
        # Un bouton touché (réponse proposée) ne peut exprimer ni détresse ni hors-sujet :
        # pas d'appel au classifieur, un appel payant de moins par réponse.
        cout_controle = 0.0
        if texte in boutons:
            signaux = {"detresse": False, "hors_sujet": False}
        else:
            signaux = self.classifieur(texte)
            cout_controle = getattr(self.classifieur, "dernier_cout", 0.0)
        consignes = []
        if signaux["detresse"]:
            db.execute(
                "INSERT INTO alertes (eleve_id, seance_id, type, extrait, cree_le) VALUES (?, ?, 'detresse', ?, ?)",
                (eleve_id, seance_id, texte[:300], maintenant_iso()),
            )
            db.commit()  # l'alerte est gardée même si le tuteur ne répond pas ensuite
            consignes.append(CONSIGNE_DETRESSE)
        elif signaux["hors_sujet"]:
            consignes.append(CONSIGNE_HORS_SUJET)
        if masque:
            consignes.append(CONSIGNE_DONNEES)
        if consigne:  # séance sans IA : ce qu'on attend de cette intervention ponctuelle
            consignes.append(consigne)
        nouveaux = [{"role": "user", "content": texte}]
        if consignes:
            nouveaux.append({"role": "system", "content": "\n".join(consignes)})
        return self._tour(db, eleve_id, seance_id, nouveaux, outils=outils, cout_initial=cout_controle)

    def conclure(self, db: sqlite3.Connection, eleve_id: int, seance_id: int) -> str:
        nouveaux = [
            {"role": "user", "content": "[L'élève termine la séance.]"},
            {"role": "system", "content": CONSIGNE_FIN},
        ]
        return self._tour(db, eleve_id, seance_id, nouveaux, outils=False)

    # --- Boucle -----------------------------------------------------------------

    def _tour(self, db, eleve_id, seance_id, nouveaux, outils=True, cout_initial=0.0) -> str:
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
        depense = cout_initial  # en dollars, cache compris (et contrôle de sécurité du message)
        texte = None

        for _ in range(MAX_APPELS_PAR_TOUR):
            reponse = self._appeler(systeme, messages, outils, EFFORT.get(seance["profil"], "medium"))
            tokens_entree += reponse.usage.input_tokens
            tokens_sortie += reponse.usage.output_tokens
            depense += cout(reponse.usage)

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
            " tokens_sortie = tokens_sortie + ?, cout_dollars = cout_dollars + ? WHERE id = ?",
            (json.dumps(messages, ensure_ascii=False), tokens_entree, tokens_sortie, depense, seance_id),
        )
        return texte

    def _appeler(self, systeme: str, messages: list, outils: bool, effort: str = "medium"):
        parametres = dict(
            model=MODELE,
            max_tokens=MAX_TOKENS,
            system=systeme,
            messages=messages,
            output_config={"effort": effort},
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
            # Visible avec « docker compose logs tuteur » (clé refusée, crédit épuisé, réseau...).
            journal.error("Appel à l'API Claude impossible : %s", e)
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
