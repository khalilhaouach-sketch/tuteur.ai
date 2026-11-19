"""Retrouve les passages du programme et des cours (docs/) sur une notion."""

from agent.tools._commun import schema
from rag.search import chercher

DEFINITION = {
    "name": "lire_programme",
    "description": (
        "Cherche dans le programme officiel et les cours du professeur les passages sur une notion d'arabe "
        "(par exemple « الفاعل » ou « حرف الباء »), au niveau de l'élève. Renvoie au plus 3 passages, "
        "chacun avec sa référence (fichier et section). N'explique que ce qui figure dans ces passages, "
        "en reprenant leurs exemples. Si aucun passage n'est trouvé, dis-le au lieu d'inventer."
    ),
    "strict": True,
    "input_schema": schema({"notion": {"type": "string"}}),
}


def executer(ctx, entree: dict) -> dict:
    notion = entree["notion"].strip()[:200]
    passages = chercher(ctx.db, notion, ctx.profil)
    if not passages:
        return {
            "notion": notion,
            "passages": [],
            "message": "Aucun passage trouvé dans le programme ni dans les cours pour cette notion.",
        }
    return {"notion": notion, "passages": passages}
