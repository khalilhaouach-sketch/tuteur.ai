"""Niveau de maîtrise de l'élève, mis à jour à partir du résultat réel de chaque exercice.

La mise à jour est faite automatiquement par corriger dès qu'un exercice est terminé (un appel d'outil
de moins par exercice). L'outil ne fait que relire l'état : l'appeler ne compte jamais un résultat deux fois.
"""

from agent import memoire
from agent.tools._commun import ErreurOutil, exercice, notion_id, schema

DEFINITION = {
    "name": "enregistrer_progression",
    "description": (
        "Relit le niveau de maîtrise d'une notion après un exercice terminé. Inutile en temps normal : "
        "corriger enregistre déjà la progression dès que l'exercice est terminé."
    ),
    "strict": True,
    "input_schema": schema({"exercice_id": {"type": "string"}}),
}

# Évolution du niveau de maîtrise (entre 0 et 1) : deux réussites du premier coup suffisent à acquérir une leçon.
GAIN_DU_PREMIER_COUP = 0.30
GAIN_APRES_ERREUR = 0.10
PERTE_ECHEC = 0.15


def _verdicts(ctx, ex_id: str) -> list[str]:
    return [l["verdict"] for l in ctx.db.execute(
        "SELECT verdict FROM tentatives WHERE eleve_id = ? AND seance_id IS ? AND exercice = ? ORDER BY id",
        (ctx.eleve_id, ctx.seance_id, ex_id),
    )]


def _etat(ctx, notion: str) -> dict:
    ligne = ctx.db.execute(
        "SELECT niveau FROM maitrise WHERE eleve_id = ? AND notion_id = ?", (ctx.eleve_id, notion_id(ctx.db, notion))
    ).fetchone()
    niveau = ligne["niveau"] if ligne else 0.0
    return {"notion": notion, "niveau_maitrise": round(niveau, 2), "acquise": niveau >= memoire.SEUIL_ACQUIS}


def appliquer(ctx, notion: str, ex_id: str) -> dict:
    """Appelé par corriger une seule fois, quand l'exercice vient de se terminer."""
    verdicts = _verdicts(ctx, ex_id)
    delta = (GAIN_DU_PREMIER_COUP if len(verdicts) == 1 else GAIN_APRES_ERREUR) if verdicts[-1] == "juste" else -PERTE_ECHEC
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
    return _etat(ctx, notion)


def executer(ctx, entree: dict) -> dict:
    notion, ex = exercice(entree["exercice_id"])
    verdicts = _verdicts(ctx, ex["id"])
    if not verdicts:
        raise ErreurOutil("aucune correction pour cet exercice : appelle d'abord corriger")
    if verdicts[-1] != "juste" and verdicts.count("faux") < 2:
        raise ErreurOutil("exercice pas encore terminé : laisse l'élève faire un deuxième essai")
    return {**_etat(ctx, notion), "enregistre": True}
