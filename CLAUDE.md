# Projet : tuteur IA de soutien scolaire (Maroc)

## Contexte
Application web mobile (PWA) où un agent IA joue le rôle d'un professeur de soutien pour 2 profils : CP arabe (P1) et 1ʳᵉ année du collège, 1AC (P2). Matière : arabe uniquement, ni français ni darija. Lis SPEC.md avant toute tâche.

## Règles
- Langue de l'interface : français ; arabe pour les contenus d'arabe.
- Public mineur : ne stocke que prénom, profil et résultats. Aucune donnée personnelle superflue.
- Les secrets (clé API) sont dans des variables d'environnement, jamais dans le code.
- L'agent tuteur n'a accès qu'aux six outils de agent/tools/. Aucun accès aux fichiers ni au shell côté élève.
- Les prompts système sont dans agent/profiles/ et ne changent que sur demande explicite.
- Chaque fonctionnalité s'accompagne de tests ; les cas de evals/ doivent passer avant de conclure.
- Avance phase par phase (voir SPEC.md) et demande ma validation à la fin de chaque phase.

## Commandes
- Installer : `pip install -r requirements.txt`
- Lancer l'API et l'interface élève : `python3 -m uvicorn apps.api.main:app --reload`
  (interface élève : http://localhost:8000/ ; page de test de l'API : http://localhost:8000/docs)
- Lancer les tests (sans appel à l'API Claude) : `python3 -m pytest`
- Réindexer docs/ à la main : `python3 -m rag.ingest` (fait aussi à chaque démarrage de l'API)
- Lancer les evals sur la vraie API (payant) : `python3 -m evals.run_evals --reel`
- Dans l'environnement cloud de Claude Code, ne jamais appeler la vraie API : utiliser le faux client de `tests/faux_claude.py`.

Variables d'environnement :
- `TUTEUR_DB` : chemin de la base SQLite (défaut : `data/tuteur.db`).
- `TUTEUR_DOCS` : dossier des programmes et des cours (défaut : `docs`).
- `ANTHROPIC_API_KEY` : clé de l'API Claude (jamais dans le code ni dans le dépôt).
- `TUTEUR_COOKIE_SECURE` : `1` par défaut (cookies réservés à HTTPS ; localhost fonctionne aussi). Ne jamais mettre `0` en production.

## Documents (docs/)
- Formats lus : .md, .txt, .docx. Les titres de section découpent les passages.
- Le niveau vient du nom du fichier ou du dossier : `cp`/`p1` → P1, `1ac`/`p2` → P2, sinon tous les niveaux.
- Banques d'exercices : `agent/tools/exercices_cp.yaml` (CP, 3 par lettre) et `agent/tools/exercices_1ac.yaml` (1AC, 3 par leçon).
  Réponses vocalisées ; un élève ne reçoit que les exercices de son niveau.
