# Tuteur IA de soutien scolaire — Architecture complète

Nov 16, 2026 · @Khalil · mis à jour le 19/11/2026 : deux profils, CP et 1AC

## Réponses directes

**Pour construire : oui, il te faut un compte payant.** Le plan gratuit n'inclut pas Claude Code. Deux voies existent : l'abonnement Pro (environ 20 $/mois), suffisant pour démarrer et réaliser le MVP, ou un compte Console API en paiement à la consommation, sans abonnement mensuel. Les formules Max (100 ou 200 $/mois) ne servent que si les limites d'usage t'interrompent souvent ([Anthropic, Claude Code avec Pro ou Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan)).

**Pour faire tourner le tuteur auprès des élèves : une clé API, facturée à part.** L'abonnement ne couvre pas l'usage de ton application en production. Chaque échange d'un élève appelle l'API de la Console, payée au volume de texte traité. Prévois donc deux budgets distincts : construire (Pro) et exploiter (API).

**Faut-il un projet complet à donner à Claude Code ? Non, un dossier de départ suffit.** Ce document joue le rôle de cahier des charges. Tu crées un dossier contenant : ce cahier des charges (`SPEC.md`), un fichier `CLAUDE.md` avec les règles du projet (voir « Plan de construction »), et les programmes officiels et tes cours dans `docs/`. Claude Code construit ensuite phase par phase : il écrit, teste et corrige le code, et tu valides la pédagogie.

Sources : [offres et accès à Claude Code](https://www.nocode.mba/articles/claude-code-pricing) et [Agent SDK et facturation](https://inventivehq.com/blog/claude-agent-sdk-guide), consultées le 16/11/2026. Les tarifs évoluent : vérifie-les sur la page officielle avant de t'abonner.

## Vision et les 3 profils

Un seul moteur d'agent sert deux profils d'élèves : chaque profil change le prompt système, le programme, le ton et l'interface. L'agent joue le rôle d'un professeur de soutien : il explique, fait pratiquer, corrige, suit la progression et rend compte aux parents.

| Profil | Niveau et matière | Interface | Style pédagogique |
| --- | --- | --- | --- |
| P1 | CP, lecture et écriture de l'arabe | Audio, très grosses lettres vocalisées, jeux courts, presque pas de texte | Répétition ludique, phrases très courtes, félicitations fréquentes |
| P2 | 1ʳᵉ année collège (1AC), arabe | Chat, exercices, correction détaillée | Guide par questions, vocabulaire adapté à l'âge |

Principes communs à tous les profils :

- L'agent guide l'élève vers la réponse au lieu de la donner d'emblée.
- Il s'appuie sur le programme officiel et sur tes cours, pas sur sa mémoire générale.
- Il se souvient des erreurs de chaque élève et y revient au bon moment.
- Un humain relit la qualité pédagogique ; l'agent complète un enseignant, il ne le remplace pas.

Confirmé : les matières du profil collège (1AC) et du CP sont uniquement l'arabe, sans français ni darija.

Confirmé : usage **personnel**, pour trois enfants de la famille. Ce n'est pas une application publique.

## Architecture et stack technique

L'application est une interface mobile reliée à un serveur central ; l'agent tuteur vit derrière ce serveur et ne parle jamais directement à l'élève.

&#91;embedded content: architecture du tuteur · 8 composants\]

L'élève et le parent passent par l'API ; l'agent appelle Claude, lit tes cours et lit et écrit la mémoire de l'élève ; la voix est un service externe relié à l'API.

### Stack proposée

| Couche | Choix proposé | Pourquoi |
| --- | --- | --- |
| Interface | PWA en React (Next.js) | s'installe sur téléphone, un seul code pour tous les écrans |
| Backend | Python, FastAPI | même langage que l'agent et les outils |
| Agent | API Claude avec tes six outils | simple et contrôlé (voir la note ci-dessous) |
| Base de données | SQLite pour le MVP, puis PostgreSQL | rien à installer au départ |
| Recherche dans les cours | recherche par similarité sur `docs/` | l'agent cite le programme au lieu de deviner |
| Voix | synthèse et reconnaissance vocales externes, choisies après tests en arabe | Claude ne produit ni n'entend d'audio |
| Hébergement | serveur cloud avec Docker | déploiement identique en test et en production |

**Précision sur l'agent.** Le Claude Agent SDK repose sur le même moteur que Claude Code, conçu pour des agents qui lisent des fichiers et lancent des commandes. Pour un tuteur destiné à des enfants, je recommande l'API Claude avec uniquement tes six outils : c'est plus simple et plus sûr. L'Agent SDK reste possible si ses outils intégrés sont désactivés.

## Structure du projet

Voici le dossier à créer avant de lancer Claude Code : l'application, l'agent, la recherche dans les cours, la voix, la base de données et les tests de qualité vivent chacun dans leur dossier.

```
tuteur-ia/
├── SPEC.md                    # ce cahier des charges
├── CLAUDE.md                  # règles du projet pour Claude Code
├── docs/
│   ├── programmes/            # programmes officiels (PDF)
│   ├── cours/                 # tes cours et exercices
│   └── pedagogie.md           # ta méthode d'enseignement
├── apps/
│   ├── web/                   # PWA mobile
│   │   ├── student/           # chat, exercices, mode CP
│   │   └── parent/            # tableau de bord parent / professeur
│   └── api/                   # backend FastAPI
│       ├── auth/              # comptes parent + sous-comptes élèves
│       ├── sessions/          # séances, limites de durée
│       └── reports/           # bilans
├── agent/
│   ├── core.py                # boucle de l'agent
│   ├── profiles/
│   │   ├── cp_arabe.md        # prompt système P1
│   │   └── college_1ac.md     # prompt système P2
│   ├── tools/
│   │   ├── lire_programme.py
│   │   ├── generer_exercice.py
│   │   ├── corriger.py
│   │   ├── enregistrer_progression.py
│   │   ├── planifier_revision.py
│   │   └── rapport_parent.py
│   └── safety/                # filtres, limites, alertes parent
├── rag/
│   ├── ingest.py              # découpe et indexe docs/
│   └── search.py
├── voice/
│   ├── tts.py                 # synthèse vocale
│   └── stt.py                 # reconnaissance vocale
├── db/
│   ├── schema.sql
│   └── migrations/
├── evals/                     # cas de test par profil
│   ├── cp_arabe.yaml
│   └── college_1ac.yaml
└── deploy/                    # Docker et configuration
```

Les dossiers `docs/` et `evals/` sont ceux que tu remplis toi-même : c'est ton expertise de professeur qui fait la qualité du tuteur.

## Agent tuteur : outils, séance et mémoire

L'agent n'invente pas ses exercices ni ses notes : il appelle six outils qui lisent le programme, écrivent en base et préparent les bilans.

| Outil | Rôle | Entrées | Sortie |
| --- | --- | --- | --- |
| `lire_programme` | Retrouve les passages du programme et de tes cours sur une notion | niveau, matière, notion | extraits + références |
| `generer_exercice` | Crée un exercice adapté à l'élève | profil, notion, difficulté, erreurs récentes | énoncé + corrigé masqué |
| `corriger` | Évalue la réponse et classe l'erreur | exercice, réponse | verdict, type d'erreur, indice |
| `enregistrer_progression` | Écrit le résultat en base | élève, notion, verdict | confirmation |
| `planifier_revision` | Fixe la prochaine révision (répétition espacée) | élève, notion, résultat | date |
| `rapport_parent` | Rédige le bilan pour le parent | élève, période | bilan lisible |

Déroulé d'une séance :

1. L'agent accueille l'élève et propose la notion à travailler, en reprenant d'abord son point faible le plus récent.
2. Il rappelle la notion en quelques phrases, appuyées sur `lire_programme`.
3. Il propose un exercice avec `generer_exercice`.
4. L'élève répond ; `corriger` rend le verdict.
5. Si la réponse est fausse : un indice, un deuxième essai, puis l'explication. Si elle est juste : l'exercice suivant est un peu plus difficile.
6. `enregistrer_progression` et `planifier_revision` sont appelés après chaque exercice.
7. En fin de séance, un récapitulatif court est donné à l'élève et le bilan part au parent.

La mémoire de l'élève vit dans la base de données, pas dans la conversation :

| Table | Contenu clé |
| --- | --- |
| `parents` | compte, e-mail, consentement |
| `eleves` | prénom, profil (P1, P2), parent rattaché |
| `notions` | matière, niveau, intitulé, lien vers le programme |
| `tentatives` | élève, notion, exercice, réponse, verdict, type d'erreur, date |
| `maitrise` | élève, notion, niveau de maîtrise, prochaine révision |
| `seances` | élève, début, fin, journal des échanges |
| `rapports` | élève, période, texte du bilan |

Au début de chaque séance, l'agent reçoit un résumé issu de `maitrise` et des dernières `tentatives` : c'est ainsi qu'il « se souvient » d'un élève d'une séance à l'autre.

## Voix, sécurité des mineurs et qualité

**Voix (surtout le CP arabe).** Claude écrit et lit du texte ; il ne produit ni n'entend d'audio. Il faut donc deux services externes : une synthèse vocale (TTS) pour lire lettres, syllabes et mots vocalisés (التشكيل), et une reconnaissance vocale (STT) pour écouter l'enfant lire. À tester sur de vrais cas avant de t'engager : la prononciation des lettres isolées et des voyelles brèves, et la reconnaissance de voix d'enfants, souvent moins fiable que celle des adultes. Le mode CP doit rester utilisable sans micro, avec des boutons de réponse.

**Sécurité des mineurs.**

- Consentement du parent à la création du compte ; sous-comptes élèves sans e-mail ni mot de passe complexe (code ou QR).
- Données minimales : prénom, profil, résultats. Pas de nom complet, pas de photo.
- L'agent reste dans la matière : hors sujet, il recentre poliment l'élève.
- Journal complet des échanges, consultable par le parent.
- Durée de séance limitée, avec pause imposée.
- Si un élève exprime une détresse, l'agent ne fait pas de thérapie : il l'encourage à parler à un adulte et prévient le parent.
- Données personnelles de mineurs : à faire valider par la CNDP (loi 09-08 au Maroc) ou un juriste avant l'ouverture au public.

**Qualité.** Le dossier `evals/` contient, pour chaque profil, des situations types : une question d'élève, une réponse fausse, une demande hors sujet, une tentative de se faire donner la réponse. Pour chacune, tu écris le comportement attendu. Les critères de relecture sont : exactitude de la langue (grammaire, orthographe, voyelles de l'arabe), niveau de langage adapté, conformité au programme, guidage sans donner la réponse. Ces tests passent à chaque modification, puis quelques élèves réels essaient l'agent sous ta supervision avant tout lancement.

## Prompts système des 2 profils

Chaque profil assemble le socle commun et son bloc spécifique ; le résultat se range dans `agent/profiles/`. Ce sont des premières versions : tu les ajusteras avec ta pratique de professeur et les tests de `evals/`.

### Socle commun (tous les profils)

```
Tu es un professeur de soutien scolaire bienveillant et rigoureux. Tu aides un élève marocain à progresser dans une matière, en complément de l'école.

MÉTHODE
- Tu guides au lieu de donner la réponse : une question, puis un indice, puis l'explication si l'élève bloque deux fois.
- Une seule question ou un seul exercice à la fois.
- Tu t'appuies sur le programme et les cours fournis par l'outil lire_programme. Si l'information n'y est pas, tu le dis au lieu d'inventer.
- Après chaque exercice, tu appelles enregistrer_progression puis planifier_revision.
- Tu encourages l'effort, pas seulement le résultat. Tu ne ridiculises jamais une erreur.

LIMITES
- Tu restes dans la matière. Hors sujet : tu recentres gentiment.
- Tu ne demandes jamais d'informations personnelles (nom complet, adresse, école, téléphone).
- Si l'élève exprime une détresse, une peur ou parle d'un danger : tu réponds avec douceur, tu l'encourages à en parler à un adulte de confiance et tu le signales au parent.
- Tu ne prétends pas être un humain.
```

### Profil P1 : style « enfant » (lecture et écriture)

```
[SOCLE COMMUN]

PROFIL : jeune enfant (style « enfant ») qui apprend à lire et à écrire l'arabe. Son palier dans le parcours et la leçon à travailler sont indiqués dans sa mémoire, au début de la séance.

LANGUE
- Tout texte arabe est entièrement vocalisé (التشكيل).
- Consignes en arabe très simple, une phrase courte à la fois. Si l'enfant semble perdu, tu reformules avec des mots encore plus simples, toujours en arabe.

CONTENU
- Le contenu de son palier : d'abord les lettres et leurs formes (début, milieu, fin de mot), les voyelles brèves, les syllabes, puis les mots simples, les premières phrases, le tracé des lettres et les premières notions de grammaire.

MÉTHODE
- Séances courtes sous forme de jeux : trouver la lettre, associer un son à un mot, compléter un mot.
- Un seul objectif par séance.
- Tu félicites chaque réussite avec enthousiasme. Après une erreur, tu redis calmement le bon son et tu proposes de réessayer.
- L'enfant peut répondre en touchant un bouton : ne l'oblige jamais à écrire un long texte.
- Tu termines par un mini-récapitulatif : la lettre ou le mot du jour.
```

### Profil P2 : style « adolescent »

```
[SOCLE COMMUN]

PROFIL : adolescent (style « adolescent »). La matière est l'arabe, et uniquement l'arabe. Son palier dans le parcours et la leçon à travailler sont indiqués dans sa mémoire, au début de la séance.

CONTENU : النحو والصرف، الإملاء، فهم النص، التعبير.

LANGUE
- Tu tutoies l'élève, avec des phrases claires et un vocabulaire de son âge.
- Tu expliques en arabe standard. Si l'élève est bloqué, tu reformules plus simplement, toujours en arabe.

MÉTHODE
- Rappel bref de la règle, un exemple, puis un exercice.
- Pour une rédaction : tu aides à trouver des idées et à faire un plan, puis tu corriges les phrases de l'élève sans réécrire son texte à sa place.
- La difficulté monte progressivement selon les réussites.
- Tu ne fournis jamais le corrigé complet d'un devoir noté.
```

## Parcours unique en paliers (phase 6)

Le contenu n'est plus organisé par classe : un seul parcours ordonné va des lettres du CP à la 1AC, en paliers
(`agent/parcours.yaml`, chaque palier ayant un identifiant fixe). Le **profil** (P1, P2) ne désigne plus une classe mais un **style** : P1 « enfant »
(grosses lettres, voix, boutons, séances de 20 min) et P2 « adolescent » (séances de 45 min).

| Paliers | Contenu |
| --- | --- |
| 1 à 3 | Les 28 lettres du CP |
| 4 à 6 | Transition : voyelles et syllabes, lecture de mots et de phrases, premières notions de grammaire |
| 7 et suivants | Le primaire (2AP à 6AP), ajouté palier par palier : 3AP et 4AP faits |
| derniers | Les 23 leçons de langue de la 1AC (4 paliers) |

- **Positionnement** : au départ, un test place l'enfant (3 questions par palier, on monte tant qu'il en réussit 2 sur 3).
- **Passage** : une question par leçon du palier ; réussi à partir de 80 %. L'enfant peut le tenter quand il veut :
  un enfant rapide valide plusieurs paliers d'affilée.
- **Confirmation** : chaque résultat de test est confirmé (ou refusé) par le parent ; le parent peut aussi placer
  l'enfant lui-même sur un palier.
- **Révision** : le tuteur peut reprendre les leçons des paliers précédents, jamais celles des paliers suivants.
- Les tests sont corrigés automatiquement avec les banques d'exercices, sans l'agent.

## Plan de construction avec Claude Code

Avance en six phases et ne passe à la suivante que lorsque le critère de la phase en cours est atteint.

1. **Fondations.** Dossier, `SPEC.md`, `CLAUDE.md`, base de données, comptes parent et élève. Critère : un parent crée un compte et un sous-compte élève.
2. **MVP arabe collège (profil P2, 1AC).** Agent, six outils, mémoire élève. Critère : une séance complète, de l'accueil au bilan, enregistrée en base.
3. **Cours et programme.** Ingestion de `docs/` pour la recherche dans tes cours. Critère : l'agent s'appuie sur le bon passage du programme.
4. **Espace parent et sécurité.** Tableau de bord, journal des échanges, limites de séance. Critère : un parent voit la progression et le journal.
5. **CP arabe avec voix.** Synthèse vocale, reconnaissance vocale, mode visuel. Critère : un enfant de CP termine un jeu de lecture, et les tests de `evals/` passent pour les deux profils.
6. **Parcours unique en paliers.** Positionnement, tests de passage, confirmation du parent, style selon l'âge. Critère : un enfant est positionné, puis passe au palier suivant après confirmation du parent.

Avant l'ouverture au public, un pilote avec quelques élèves réels, sous ta supervision.

### `CLAUDE.md` à placer à la racine

```
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
À compléter pendant la phase 1 : lancer l'API, l'interface et les tests.
```

### Premier message à donner à Claude Code

```
Lis SPEC.md et CLAUDE.md. Commence la phase 1 : crée l'ossature du projet selon la structure décrite, le schéma de base de données (db/schema.sql) et l'authentification parent / sous-comptes élèves. Explique tes choix techniques avant de coder et attends ma validation.
```

### Coûts

- **Construire** : l'abonnement Pro, tant que les limites d'usage ne te bloquent pas.
- **Faire tourner** : l'API, facturée au volume de texte échangé. Le coût réel dépend du nombre d'élèves et de la longueur des séances : mesure-le pendant la phase 2 en comptant les tokens d'une séance type.
- **À côté** : hébergement, base de données, services de voix (phase 5). Un modèle plus léger peut suffire pour générer des exercices, et un modèle plus puissant pour corriger les rédactions : à tester.

## Prompts de chaque phase

Le prompt de la phase 1 est donné plus haut. Colle les suivants un par un, seulement après avoir validé la phase précédente.

### Phase 2 : MVP du profil P2 (1AC, arabe)

```
Phase 1 validée. Commence la phase 2 : le MVP du profil P2 (1AC, arabe). Implémente l'agent tuteur avec l'API Claude et les six outils décrits dans SPEC.md (lire_programme peut renvoyer pour l'instant un petit jeu de données d'exemple), la boucle de séance décrite dans SPEC.md, la mémoire élève en base et une interface de chat minimale. Charge le prompt système depuis agent/profiles/college_1ac.md et lis la clé API dans la variable d'environnement ANTHROPIC_API_KEY, sans jamais l'écrire dans le code. Dans cet environnement cloud, n'appelle pas la vraie API : utilise des réponses simulées pour les tests. Ajoute des cas de test de base dans evals/college_1ac.yaml, lance les tests et montre-moi une séance complète avant de continuer.
```

### Phase 3 : cours et programme

```
Phase 2 validée. Commence la phase 3 : ingère les documents de docs/programmes et docs/cours dans une recherche par similarité (rag/ingest.py et rag/search.py), puis branche l'outil lire_programme dessus. L'agent doit citer le passage utilisé. Teste avec trois notions et montre-moi les extraits retrouvés.
```

### Phase 4 : espace parent et sécurité

```
Phase 3 validée. Commence la phase 4 : l'espace parent (apps/web/parent) avec connexion, liste des élèves, progression par notion, journal des échanges et bilan généré par l'outil rapport_parent. Ajoute dans agent/safety/ les limites de durée de séance, le recentrage des demandes hors sujet et l'alerte au parent en cas de détresse. Montre-moi les écrans et les tests.
```

### Phase 5 : CP arabe avec voix

```
Phase 4 validée. Commence la phase 5 : ajoute le profil P1 avec agent/profiles/cp_arabe.md et le mode visuel pour enfant (grosses lettres vocalisées, boutons de réponse, jeux courts). Avant d'intégrer la voix, propose-moi deux ou trois services de synthèse et de reconnaissance vocales à tester en arabe, avec leurs limites. Une fois mon choix fait, intègre-le dans voice/ en gardant un mode utilisable sans micro.
```
