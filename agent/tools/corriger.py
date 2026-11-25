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
        "erreur). Passe la réponse de l'élève exactement telle qu'il l'a écrite, avec ses voyelles. Quand l'exercice "
        "est terminé, la progression et la révision sont enregistrées, et « exercice_suivant » donne le prochain "
        "exercice du palier (énoncé et exercice_id) : présente-le directement, sans appeler d'autre outil."
    ),
    "strict": True,
    "input_schema": schema(
        {
            "exercice_id": {"type": "string"},
            "reponse": {"type": "string"},
        }
    ),
}


def evaluer(ex: dict, reponse: str) -> tuple[str, str | None]:
    """Verdict (« juste », « faux » ou « a_vocaliser ») et type d'erreur d'une réponse à un exercice."""
    tolerer = ex.get("tolerer_hamza", True)
    obligatoires = ex.get("voyelles_obligatoires", False)
    resultats = [comparer(reponse, r, obligatoires, tolerer) for r in ex["reponses"]]
    if "juste" in resultats:
        return "juste", None
    if "a_vocaliser" in resultats:
        return "a_vocaliser", None
    return "faux", _type_erreur(reponse, ex, tolerer, voyelles_seulement="voyelles" in resultats)


def executer(ctx, entree: dict) -> dict:
    notion, ex = exercice(entree["exercice_id"])
    reponse = entree["reponse"].strip()[:500]
    verdict, type_erreur = evaluer(ex, reponse)
    if verdict == "a_vocaliser":
        # Bonnes lettres, voyelles justes mais manquantes : on redemande, sans compter d'erreur.
        return {"verdict": "a_vocaliser", "exercice_termine": False,
                "consigne": "Demande à l'élève de réécrire sa réponse avec toutes les voyelles (الشَّكْل)."}
    juste = verdict == "juste"

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
        return _terminer(ctx, notion, ex, {"verdict": "juste", "exercice_termine": True, "essais_rates": nb_erreurs})
    if nb_erreurs == 1:
        return {"verdict": "faux", "type_erreur": type_erreur, "indice": ex["indice"], "exercice_termine": False}
    return _terminer(ctx, notion, ex, {
        "verdict": "faux",
        "type_erreur": type_erreur,
        "explication": ex["explication"],
        "bonne_reponse": ex["reponses"][0],
        "exercice_termine": True,
    })


def _terminer(ctx, notion: str, ex: dict, resultat: dict) -> dict:
    """Exercice terminé : progression, révision et exercice suivant du palier, dans le même appel d'outil."""
    from agent.tools import enregistrer_progression, generer_exercice, planifier_revision

    progression = enregistrer_progression.appliquer(ctx, notion, ex["id"])
    planifier_revision.planifier(ctx, notion)
    return {**resultat, "niveau_maitrise": progression["niveau_maitrise"], "lecon_acquise": progression["acquise"],
            "exercice_suivant": generer_exercice.exercice_suivant(ctx)}


def _type_erreur(reponse: str, ex: dict, tolerer: bool, voyelles_seulement: bool) -> str:
    for cle, type_erreur in ex["erreurs"].items():
        if a_des_voyelles(cle):
            if comparer(reponse, cle, False, tolerer) == "juste":
                return type_erreur
        elif normaliser(reponse, tolerer) == normaliser(cle, tolerer):
            return type_erreur
    return "خطأ في الشكل (الحركات)" if voyelles_seulement else "erreur non répertoriée"
