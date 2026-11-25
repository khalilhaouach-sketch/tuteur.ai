"""Choisit un exercice adapté à l'élève. Le corrigé reste côté serveur (jamais envoyé au modèle)."""

from agent.tools._commun import NOMS_NOTIONS, ErreurOutil, choix_de_l_enonce, notion_id, notion_valide, schema
from agent.tools.donnees_exemple import NOTIONS

DEFINITION = {
    "name": "generer_exercice",
    "description": (
        "Propose un exercice sur une notion du palier de l'élève (ou d'un palier précédent, pour réviser), au niveau de difficulté demandé (1 facile, 2 moyen, 3 difficile). "
        "Renvoie l'énoncé à présenter tel quel à l'élève et un exercice_id à passer ensuite à corriger. "
        "Le corrigé n'est pas fourni : seul l'outil corriger le connaît. "
        "Indique aussi les erreurs récentes de l'élève sur cette notion. Si « choix » n'est pas vide, les choix "
        "s'affichent en boutons sous ton message : demande à l'élève de toucher la bonne réponse."
    ),
    "strict": True,
    "input_schema": schema(
        {
            "notion": {"type": "string", "enum": NOMS_NOTIONS},
            "difficulte": {"type": "integer", "enum": [1, 2, 3]},
        }
    ),
}


def executer(ctx, entree: dict) -> dict:
    notion = notion_valide(entree["notion"])
    difficulte = entree["difficulte"]
    from agent import parcours

    numero = palier_de_l_eleve(ctx)
    if notion not in parcours.notions_accessibles(numero):
        actuelles = parcours.palier(numero)["notions"]
        raise ErreurOutil(
            f"notion au-delà du palier de l'élève (palier {numero}). Notions de son palier : {', '.join(actuelles)}"
        )
    nid = notion_id(ctx.db, notion)

    deja_reussis = {
        r["exercice"]
        for r in ctx.db.execute(
            "SELECT exercice FROM tentatives WHERE eleve_id = ? AND seance_id IS ? AND verdict = 'juste'",
            (ctx.eleve_id, ctx.seance_id),
        )
    }
    candidats = [e for e in NOTIONS[notion]["exercices"] if e["id"] not in deja_reussis]
    if not candidats:
        return {"notion": notion, "message": "Tous les exercices de cette notion sont réussis dans cette séance."}
    # Le plus proche de la difficulté demandée.
    choisi = min(candidats, key=lambda e: (abs(e["difficulte"] - difficulte), e["difficulte"]))

    erreurs_recentes = [
        r["type_erreur"]
        for r in ctx.db.execute(
            "SELECT type_erreur FROM tentatives WHERE eleve_id = ? AND notion_id = ?"
            " AND type_erreur IS NOT NULL ORDER BY id DESC LIMIT 3",
            (ctx.eleve_id, nid),
        )
    ]
    return {
        "exercice_id": choisi["id"],
        "notion": notion,
        "difficulte": choisi["difficulte"],
        "enonce": choisi["enonce"],
        # Choix affichés en boutons dans l'application (exercices du CP) : l'enfant n'a pas à écrire.
        "choix": choix_de_l_enonce(choisi["enonce"]),
        "erreurs_recentes": erreurs_recentes,
    }


def palier_de_l_eleve(ctx) -> int:
    from agent import parcours

    return parcours.palier_eleve(ctx.db, ctx.eleve_id) or 1


def exercice_suivant(ctx) -> dict:
    """Exercice suivant de la séance, en avançant dans le palier : leçon par leçon, la première non acquise,
    du plus facile au plus difficile. Évite de faire appeler un outil de plus au modèle."""
    from agent import memoire, parcours

    termines = {
        r["exercice"]
        for r in ctx.db.execute(
            "SELECT exercice FROM tentatives WHERE eleve_id = ? AND seance_id IS ?"
            " GROUP BY exercice HAVING SUM(verdict = 'juste') > 0 OR SUM(verdict = 'faux') >= 2",
            (ctx.eleve_id, ctx.seance_id),
        )
    }
    jamais_reussis = lambda e: e["id"] not in reussis_un_jour  # noqa: E731
    reussis_un_jour = {
        r["exercice"]
        for r in ctx.db.execute("SELECT DISTINCT exercice FROM tentatives WHERE eleve_id = ? AND verdict = 'juste'",
                                (ctx.eleve_id,))
    }
    palier = parcours.palier(palier_de_l_eleve(ctx))
    premiere = memoire.lecon_suivante(ctx.db, ctx.eleve_id)
    if premiere is None:
        return {"palier_termine": True,
                "consigne": "Toutes les leçons du palier sont acquises : félicite l'élève et propose le test de passage."}
    lecons = palier["notions"][palier["notions"].index(premiere):]
    for notion in lecons:
        if not memoire.lecon_acquise(ctx.db, ctx.eleve_id, notion):
            restants = [e for e in NOTIONS[notion]["exercices"] if e["id"] not in termines]
            if restants:
                # D'abord les exercices jamais réussis (variété d'une séance à l'autre), du plus facile au plus dur.
                choisi = min(restants, key=lambda e: (not jamais_reussis(e), e["difficulte"]))
                return {"exercice_id": choisi["id"], "notion": notion, "enonce": choisi["enonce"],
                        "choix": choix_de_l_enonce(choisi["enonce"])}
    return {"consigne": "Plus d'exercice nouveau pour ce palier dans cette séance : fais un court bilan et "
                        "propose de terminer la séance."}
