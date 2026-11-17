# Projet : tuteur IA de soutien scolaire (Maroc)

## Contexte
Application web mobile (PWA) où un agent IA joue le rôle d'un professeur de soutien pour 3 profils : CP arabe (P1), 2AC (P2), 3AC (P3). Matière : arabe uniquement, ni français ni darija. Lis SPEC.md avant toute tâche.

## Règles
- Langue de l'interface : français ; arabe pour les contenus d'arabe.
- Public mineur : ne stocke que prénom, profil et résultats. Aucune donnée personnelle superflue.
- Les secrets (clé API) sont dans des variables d'environnement, jamais dans le code.
- L'agent tuteur n'a accès qu'aux six outils de agent/tools/. Aucun accès aux fichiers ni au shell côté élève.
- Les prompts système sont dans agent/profiles/ et ne changent que sur demande explicite.
- Chaque fonctionnalité s'accompagne de tests ; les cas de evals/ doivent passer avant de conclure.
- Avance phase par phase (voir SPEC.md) et demande ma validation à la fin de chaque phase.

## Commandes
À compléter pendant la phase 1 : lancer l'API, l'interface et les tests.
