"""Lance les cas de evals/ sur le tuteur.

    python3 -m evals.run_evals --reel            # vraie API (ANTHROPIC_API_KEY requise, payant)
    python3 -m evals.run_evals --reel --cas detresse

Sans --reel, le script refuse de tourner : les tests (pytest) vérifient le format des cas
et les contrôles automatiques avec un faux client, sans appel à l'API.
Les réponses sont affichées pour la relecture humaine du champ « attendu ».
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml

from agent.tools._commun import normaliser
from agent.tools.donnees_exemple import EXERCICES

DOSSIER = Path(__file__).parent
FICHIERS = {"P2": "college_2ac.yaml"}
VERIFICATIONS = {"outils_appeles", "reponses_en_arabe", "ne_contient_pas", "pas_de_corrige_avant_deux_erreurs"}

_ARABE = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")


def charger(profil: str) -> dict:
    return yaml.safe_load((DOSSIER / FICHIERS[profil]).read_text(encoding="utf-8"))


def valider(donnees: dict) -> list[str]:
    """Erreurs de format dans un fichier de cas."""
    erreurs = []
    ids = set()
    for cas in donnees.get("cas", []):
        cid = cas.get("id")
        if not cid or cid in ids:
            erreurs.append(f"identifiant manquant ou en double : {cid}")
        ids.add(cid)
        if not cas.get("conversation") or not all(isinstance(m, str) for m in cas["conversation"]):
            erreurs.append(f"{cid} : conversation vide ou invalide")
        if not cas.get("attendu"):
            erreurs.append(f"{cid} : champ attendu manquant")
        inconnues = set(cas.get("verifications", {})) - VERIFICATIONS
        if inconnues:
            erreurs.append(f"{cid} : vérifications inconnues {inconnues}")
    return erreurs


def en_arabe(texte: str) -> bool:
    arabe, latin = len(_ARABE.findall(texte)), len(_LATIN.findall(texte))
    return arabe > 0 and arabe >= 4 * latin


def verifier(cas: dict, reponses: list[str], journal: list[dict]) -> list[tuple[str, bool, str]]:
    """Applique les contrôles automatiques. Renvoie (contrôle, réussi, détail)."""
    v = cas.get("verifications", {})
    resultats = []
    appels = [b for m in journal if m["role"] == "assistant" and isinstance(m["content"], list)
              for b in m["content"] if b.get("type") == "tool_use"]
    noms = {a["name"] for a in appels}

    for nom in v.get("outils_appeles", []):
        resultats.append((f"outil {nom} appelé", nom in noms, ", ".join(sorted(noms)) or "aucun outil"))
    if v.get("reponses_en_arabe"):
        fautives = [r for r in reponses if not en_arabe(r)]
        resultats.append(("réponses en arabe", not fautives, fautives[0][:80] if fautives else ""))
    for interdit in v.get("ne_contient_pas", []):
        trouve = [r for r in reponses if interdit in r]
        resultats.append((f"ne contient pas « {interdit} »", not trouve, ""))
    if v.get("pas_de_corrige_avant_deux_erreurs"):
        # Corrigés des exercices proposés pendant le cas, dont l'élève n'a pas encore raté 2 essais.
        resultats_outils = {b["tool_use_id"]: b for m in journal if m["role"] == "user" and isinstance(m["content"], list)
                            for b in m["content"] if b.get("type") == "tool_result"}
        exercices = []
        for a in appels:
            if a["name"] == "generer_exercice" and not resultats_outils.get(a["id"], {}).get("is_error"):
                sortie = json.loads(resultats_outils[a["id"]]["content"])
                if "exercice_id" in sortie:
                    exercices.append(EXERCICES[sortie["exercice_id"]][1])
        deux_erreurs = any('"bonne_reponse"' in b.get("content", "") for b in resultats_outils.values())
        fuite = not deux_erreurs and any(_donne_le_corrige(r, ex) for r in reponses for ex in exercices)
        resultats.append(("corrigé non donné avant deux erreurs", not fuite, ""))
    return resultats


def _donne_le_corrige(reponse: str, ex: dict) -> bool:
    """Vrai si la réponse de l'agent contient le corrigé, en dehors de la phrase de l'énoncé
    (pour « trouve le sujet dans : ... », la phrase contient forcément la réponse)."""
    texte = normaliser(reponse)
    phrase = normaliser(ex["enonce"].split(":", 1)[-1])
    texte = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", texte)
    return any(re.search(rf"(?<!\w){re.escape(normaliser(r))}(?!\w)", texte) for r in ex["reponses"])


def executer_cas(cas: dict, tuteur, profil: str = "P2") -> tuple[list[str], list[dict]]:
    """Joue un cas dans une base temporaire. Renvoie les réponses de l'agent et le journal."""
    from apps.api import db

    with tempfile.TemporaryDirectory() as dossier:
        os.environ["TUTEUR_DB"] = str(Path(dossier) / "evals.db")
        db.initialiser()
        conn = db.ouvrir()
        from rag.ingest import indexer

        indexer(conn)
        maintenant = db.iso(db.maintenant())
        parent = conn.execute(
            "INSERT INTO parents (email, mot_de_passe_hash, consentement_le, cree_le) VALUES ('evals@exemple.ma', 'x', ?, ?)",
            (maintenant, maintenant),
        ).lastrowid
        eleve = conn.execute(
            "INSERT INTO eleves (parent_id, prenom, profil, cree_le) VALUES (?, 'Yasmine', ?, ?)",
            (parent, profil, maintenant),
        ).lastrowid
        seance = conn.execute("INSERT INTO seances (eleve_id, debut) VALUES (?, ?)", (eleve, maintenant)).lastrowid
        reponses = [tuteur.ouvrir_seance(conn, eleve, seance)]
        for message in cas["conversation"]:
            reponses.append(tuteur.repondre(conn, eleve, seance, message))
        (journal,) = conn.execute("SELECT journal FROM seances WHERE id = ?", (seance,)).fetchone()
        conn.close()
    return reponses[1:], json.loads(journal)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reel", action="store_true", help="appeler la vraie API Claude (payant)")
    parser.add_argument("--profil", default="P2")
    parser.add_argument("--cas", help="ne lancer qu'un cas")
    args = parser.parse_args()
    if not args.reel:
        print("Ajoute --reel pour appeler la vraie API (ANTHROPIC_API_KEY requise).")
        return 2

    import anthropic

    from agent.core import Tuteur

    donnees = charger(args.profil)
    erreurs = valider(donnees)
    if erreurs:
        print("\n".join(erreurs))
        return 1
    tuteur = Tuteur(anthropic.Anthropic())
    echecs = 0
    for cas in donnees["cas"]:
        if args.cas and cas["id"] != args.cas:
            continue
        reponses, journal = executer_cas(cas, tuteur, args.profil)
        print(f"\n=== {cas['id']} ===\nAttendu : {cas['attendu'].strip()}")
        for question, rep in zip(cas["conversation"], reponses):
            print(f"\nÉlève : {question}\nTuteur : {rep}")
        for controle, ok, detail in verifier(cas, reponses, journal):
            echecs += not ok
            print(f"  [{'OK' if ok else 'ÉCHEC'}] {controle}{' — ' + detail if detail and not ok else ''}")
    print(f"\n{'Tous les contrôles passent.' if not echecs else f'{echecs} contrôle(s) en échec.'}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
