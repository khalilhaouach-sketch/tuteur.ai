"""Rédige le bilan destiné au parent, à partir des résultats enregistrés (pas de texte inventé)."""

from datetime import timedelta

from agent.db_utils import iso, maintenant
from agent.tools._commun import schema

DEFINITION = {
    "name": "rapport_parent",
    "description": (
        "Rédige et enregistre le bilan de l'élève pour son parent sur les derniers jours "
        "(exercices faits, réussites, erreurs fréquentes, prochaines révisions)."
    ),
    "strict": True,
    "input_schema": schema({"periode_jours": {"type": "integer", "enum": [1, 7, 30]}}),
}


def rediger(ctx, periode_jours: int) -> str:
    fin = maintenant()
    debut = fin - timedelta(days=periode_jours)
    (prenom,) = ctx.db.execute("SELECT prenom FROM eleves WHERE id = ?", (ctx.eleve_id,)).fetchone()

    lignes = ctx.db.execute(
        "SELECT n.intitule, t.exercice, t.verdict, t.type_erreur FROM tentatives t"
        " JOIN notions n ON n.id = t.notion_id WHERE t.eleve_id = ? AND t.cree_le >= ? ORDER BY t.id",
        (ctx.eleve_id, iso(debut)),
    ).fetchall()
    titre = "aujourd'hui" if periode_jours == 1 else f"sur les {periode_jours} derniers jours"
    if not lignes:
        texte = f"Bilan de {prenom} {titre} : aucun exercice réalisé."
    else:
        parties = [f"Bilan de {prenom} {titre} :"]
        par_notion: dict[str, dict] = {}
        for l in lignes:
            d = par_notion.setdefault(l["intitule"], {"exercices": set(), "reussis": set(), "erreurs": {}})
            d["exercices"].add(l["exercice"])
            if l["verdict"] == "juste":
                d["reussis"].add(l["exercice"])
            elif l["type_erreur"]:
                d["erreurs"][l["type_erreur"]] = d["erreurs"].get(l["type_erreur"], 0) + 1
        for notion, d in par_notion.items():
            ligne = f"- {notion} : {len(d['reussis'])} exercice(s) réussi(s) sur {len(d['exercices'])}."
            if d["erreurs"]:
                principale = max(d["erreurs"], key=d["erreurs"].get)
                ligne += f" Erreur la plus fréquente : {principale}."
            parties.append(ligne)
        revisions = ctx.db.execute(
            "SELECT n.intitule, m.prochaine_revision FROM maitrise m JOIN notions n ON n.id = m.notion_id"
            " WHERE m.eleve_id = ? AND m.prochaine_revision IS NOT NULL ORDER BY m.prochaine_revision",
            (ctx.eleve_id,),
        ).fetchall()
        if revisions:
            parties.append(
                "Prochaines révisions : "
                + ", ".join(f"{r['intitule']} le {r['prochaine_revision']}" for r in revisions)
                + "."
            )
        texte = "\n".join(parties)

    ctx.db.execute(
        "INSERT INTO rapports (eleve_id, periode_debut, periode_fin, texte, cree_le) VALUES (?, ?, ?, ?, ?)",
        (ctx.eleve_id, iso(debut), iso(fin), texte, iso(fin)),
    )
    return texte


def executer(ctx, entree: dict) -> dict:
    return {"bilan": rediger(ctx, entree["periode_jours"]), "envoye_au_parent": True}
