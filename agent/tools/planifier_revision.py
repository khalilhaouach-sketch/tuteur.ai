"""Fixe la prochaine révision d'une notion (répétition espacée)."""

from datetime import timedelta

from agent.db_utils import maintenant
from agent.tools._commun import ErreurOutil, NOMS_NOTIONS, notion_id, notion_valide, schema

DEFINITION = {
    "name": "planifier_revision",
    "description": (
        "Fixe la date de la prochaine révision d'une notion selon le niveau de maîtrise de l'élève "
        "(répétition espacée). À appeler après enregistrer_progression. La date est interne : "
        "ne l'annonce pas à l'élève et ne t'arrête pas pour autant."
    ),
    "strict": True,
    "input_schema": schema({"notion": {"type": "string", "enum": NOMS_NOTIONS}}),
}


def intervalle_jours(niveau: float) -> int:
    if niveau < 0.3:
        return 1
    if niveau < 0.6:
        return 3
    if niveau < 0.85:
        return 7
    return 14


def executer(ctx, entree: dict) -> dict:
    notion = notion_valide(entree["notion"])
    nid = notion_id(ctx.db, notion)
    ligne = ctx.db.execute(
        "SELECT niveau FROM maitrise WHERE eleve_id = ? AND notion_id = ?", (ctx.eleve_id, nid)
    ).fetchone()
    if ligne is None:
        raise ErreurOutil("aucune progression enregistrée : appelle d'abord enregistrer_progression")
    jours = intervalle_jours(ligne["niveau"])
    date = (maintenant() + timedelta(days=jours)).date().isoformat()
    ctx.db.execute(
        "UPDATE maitrise SET prochaine_revision = ? WHERE eleve_id = ? AND notion_id = ?",
        (date, ctx.eleve_id, nid),
    )
    return {"notion": notion, "prochaine_revision": date, "dans_jours": jours}
