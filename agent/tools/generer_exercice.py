"""Choisit un exercice adapté à l'élève. Le corrigé reste côté serveur (jamais envoyé au modèle)."""

from agent.tools._commun import NOMS_NOTIONS, notion_id, notion_valide, schema
from agent.tools.donnees_exemple import NOTIONS

DEFINITION = {
    "name": "generer_exercice",
    "description": (
        "Propose un exercice sur une notion, au niveau de difficulté demandé (1 facile, 2 moyen, 3 difficile). "
        "Renvoie l'énoncé à présenter tel quel à l'élève et un exercice_id à passer ensuite à corriger. "
        "Le corrigé n'est pas fourni : seul l'outil corriger le connaît. "
        "Indique aussi les erreurs récentes de l'élève sur cette notion."
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
        "erreurs_recentes": erreurs_recentes,
    }
