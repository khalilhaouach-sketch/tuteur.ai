"""Met à jour le niveau de maîtrise de l'élève à partir du résultat réel de l'exercice."""

from agent import memoire
from agent.tools._commun import ErreurOutil, exercice, notion_id, schema

DEFINITION = {
    "name": "enregistrer_progression",
    "description": (
        "Enregistre en base le résultat d'un exercice terminé (après le verdict final de corriger) "
        "et met à jour le niveau de maîtrise de la notion. Le résultat est lu depuis les corrections, "
        "il n'a pas à être fourni. Indique si la leçon est acquise et, dans ce cas, la leçon suivante "
        "du parcours, à commencer dans la même séance."
    ),
    "strict": True,
    "input_schema": schema({"exercice_id": {"type": "string"}}),
}

# Évolution du niveau de maîtrise (entre 0 et 1).
GAIN_DU_PREMIER_COUP = 0.25
GAIN_APRES_ERREUR = 0.10
PERTE_ECHEC = 0.15


def executer(ctx, entree: dict) -> dict:
    notion, ex = exercice(entree["exercice_id"])
    lignes = ctx.db.execute(
        "SELECT verdict FROM tentatives WHERE eleve_id = ? AND seance_id IS ? AND exercice = ? ORDER BY id",
        (ctx.eleve_id, ctx.seance_id, ex["id"]),
    ).fetchall()
    if not lignes:
        raise ErreurOutil("aucune correction pour cet exercice : appelle d'abord corriger")
    verdicts = [l["verdict"] for l in lignes]
    if verdicts[-1] == "juste":
        delta = GAIN_DU_PREMIER_COUP if len(verdicts) == 1 else GAIN_APRES_ERREUR
    elif verdicts.count("faux") >= 2:
        delta = -PERTE_ECHEC
    else:
        raise ErreurOutil("exercice pas encore terminé : laisse l'élève faire un deuxième essai")

    nid = notion_id(ctx.db, notion)
    ctx.db.execute(
        "INSERT INTO maitrise (eleve_id, notion_id, niveau) VALUES (?, ?, 0)"
        " ON CONFLICT (eleve_id, notion_id) DO NOTHING",
        (ctx.eleve_id, nid),
    )
    ctx.db.execute(
        "UPDATE maitrise SET niveau = MIN(1, MAX(0, niveau + ?)) WHERE eleve_id = ? AND notion_id = ?",
        (delta, ctx.eleve_id, nid),
    )
    (niveau,) = ctx.db.execute(
        "SELECT niveau FROM maitrise WHERE eleve_id = ? AND notion_id = ?", (ctx.eleve_id, nid)
    ).fetchone()
    resultat = {"notion": notion, "niveau_maitrise": round(niveau, 2), "enregistre": True,
                "acquise": niveau >= memoire.SEUIL_ACQUIS}
    if resultat["acquise"]:
        # Pas d'arrêt sur une leçon acquise : on enchaîne sur la suivante du palier.
        suivante = memoire.lecon_suivante(ctx.db, ctx.eleve_id)
        resultat["lecon_suivante"] = suivante or "aucune : toutes les leçons du palier sont acquises, propose le test de passage"
    return resultat
