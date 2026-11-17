"""Évalue la réponse de l'élève, classe l'erreur et enregistre la tentative."""

from agent.tools._commun import exercice, normaliser, notion_id, schema
from agent.db_utils import maintenant_iso

DEFINITION = {
    "name": "corriger",
    "description": (
        "Corrige la réponse de l'élève à un exercice. Renvoie le verdict (juste ou faux), le type d'erreur, "
        "et selon l'essai : un indice après la première erreur, puis l'explication et la bonne réponse "
        "après la deuxième erreur. Passe la réponse de l'élève telle qu'il l'a écrite."
    ),
    "strict": True,
    "input_schema": schema(
        {
            "exercice_id": {"type": "string"},
            "reponse": {"type": "string"},
        }
    ),
}


def executer(ctx, entree: dict) -> dict:
    notion, ex = exercice(entree["exercice_id"])
    reponse = entree["reponse"].strip()[:500]
    tolerer = ex.get("tolerer_hamza", True)
    normalisee = normaliser(reponse, tolerer)

    juste = normalisee in {normaliser(r, tolerer) for r in ex["reponses"]}
    type_erreur = None
    if not juste:
        connues = {normaliser(k, tolerer): v for k, v in ex["erreurs"].items()}
        type_erreur = connues.get(normalisee, "erreur non répertoriée")

    ctx.db.execute(
        "INSERT INTO tentatives (eleve_id, notion_id, seance_id, exercice, reponse, verdict, type_erreur, cree_le)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ctx.eleve_id, notion_id(ctx.db, notion), ctx.seance_id, ex["id"], reponse,
         "juste" if juste else "faux", type_erreur, maintenant_iso()),
    )
    (nb_erreurs,) = ctx.db.execute(
        "SELECT COUNT(*) FROM tentatives WHERE eleve_id = ? AND seance_id IS ? AND exercice = ? AND verdict = 'faux'",
        (ctx.eleve_id, ctx.seance_id, ex["id"]),
    ).fetchone()

    if juste:
        return {"verdict": "juste", "exercice_termine": True, "essais_rates": nb_erreurs}
    if nb_erreurs == 1:
        return {"verdict": "faux", "type_erreur": type_erreur, "indice": ex["indice"], "exercice_termine": False}
    return {
        "verdict": "faux",
        "type_erreur": type_erreur,
        "explication": ex["explication"],
        "bonne_reponse": ex["reponses"][0],
        "exercice_termine": True,
    }
