"""Évalue la réponse de l'élève, classe l'erreur et enregistre la tentative."""

from agent.tools._commun import a_des_voyelles, comparer, exercice, normaliser, notion_id, schema
from agent.db_utils import maintenant_iso

DEFINITION = {
    "name": "corriger",
    "description": (
        "Corrige la réponse de l'élève à un exercice, voyelles comprises. Renvoie le verdict (juste ou faux), "
        "le type d'erreur, et selon l'essai : un indice après la première erreur, puis l'explication et la bonne "
        "réponse après la deuxième erreur. Le verdict « a_vocaliser » signifie que la réponse est juste mais "
        "incomplète : demande à l'élève de la réécrire avec toutes les voyelles (ce n'est pas compté comme une "
        "erreur). Passe la réponse de l'élève exactement telle qu'il l'a écrite, avec ses voyelles."
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
    obligatoires = ex.get("voyelles_obligatoires", False)

    resultats = [comparer(reponse, r, obligatoires, tolerer) for r in ex["reponses"]]
    juste = "juste" in resultats
    if not juste and "a_vocaliser" in resultats:
        # Bonnes lettres, voyelles justes mais manquantes : on redemande, sans compter d'erreur.
        return {"verdict": "a_vocaliser", "exercice_termine": False,
                "consigne": "Demande à l'élève de réécrire sa réponse avec toutes les voyelles (الشَّكْل)."}
    type_erreur = None
    if not juste:
        type_erreur = _type_erreur(reponse, ex, tolerer, voyelles_seulement="voyelles" in resultats)

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


def _type_erreur(reponse: str, ex: dict, tolerer: bool, voyelles_seulement: bool) -> str:
    for cle, type_erreur in ex["erreurs"].items():
        if a_des_voyelles(cle):
            if comparer(reponse, cle, False, tolerer) == "juste":
                return type_erreur
        elif normaliser(reponse, tolerer) == normaliser(cle, tolerer):
            return type_erreur
    return "خطأ في الشكل (الحركات)" if voyelles_seulement else "erreur non répertoriée"
