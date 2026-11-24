# Projet : tuteur IA de soutien scolaire (Maroc)

## Contexte
Application web mobile (PWA) où un agent IA joue le rôle d'un professeur de soutien sur un parcours unique en paliers, des lettres du CP à la 1AC (`agent/parcours.yaml`). Le profil est un style : P1 « enfant », P2 « adolescent ». Matière : arabe uniquement, ni français ni darija. Usage personnel : tuteur familial pour trois enfants (pas une application publique). Lis SPEC.md avant toute tâche.

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
- Utilisation à la maison (Wi-Fi, sans HTTPS) : `python3 lancer_maison.py` ; guide pour la famille : INSTALLATION.md
- Mise en ligne (serveur + domaine, HTTPS par Caddy) : `sudo bash deploy/installer_serveur.sh` ; guide : DEPLOIEMENT.md
  (compose.yml à la racine ; le tuteur n'est joignable que par Caddy ; uvicorn avec --proxy-headers)
- Lancer l'API et l'interface élève : `python3 -m uvicorn apps.api.main:app --reload`
  (interface élève : http://localhost:8000/ ; page de test de l'API : http://localhost:8000/docs)
- Lancer les tests (sans appel à l'API Claude) : `python3 -m pytest`
- Réindexer docs/ à la main : `python3 -m rag.ingest` (fait aussi à chaque démarrage de l'API)
- Lancer les evals sur la vraie API (payant) : `python3 -m evals.run_evals --reel --profil P2` (et `--profil P1` pour le CP)
- Dans l'environnement cloud de Claude Code, ne jamais appeler la vraie API : utiliser le faux client de `tests/faux_claude.py`.

Variables d'environnement :
- `TUTEUR_DB` : chemin de la base SQLite (défaut : `data/tuteur.db`).
- `TUTEUR_DOCS` : dossier des programmes et des cours (défaut : `docs`).
- `ANTHROPIC_API_KEY` : clé de l'API Claude (jamais dans le code ni dans le dépôt ; à la maison, dans `.env`, exclu de Git).
- `TUTEUR_COOKIE_SECURE` : `1` par défaut (cookies réservés à HTTPS ; localhost fonctionne aussi). Ne jamais mettre `0` en production.

## Documents (docs/)
- Formats lus : .md, .txt, .docx. Les titres de section découpent les passages.
- Le tuteur cherche dans tous les cours (le parcours mélange les niveaux) ; les fichiers commencent par `cp_`, `1ac_` ou `parcours_` (transition, primaire).
- Banques d'exercices : `agent/tools/exercices_cp.yaml`, `exercices_transition.yaml`, `exercices_primaire.yaml`, `exercices_1ac.yaml` (3 par leçon).
  Réponses vocalisées ; un élève ne reçoit que les exercices de son palier et des paliers précédents.
- Parcours : `agent/parcours.yaml` (ordre des paliers, identifiants fixes enregistrés en base, seuil de passage 80 %) ;
  tests : `agent/evaluation.py`. Après une modification du parcours : `python3 -m agent.parcours` (régénère PARCOURS.md).
