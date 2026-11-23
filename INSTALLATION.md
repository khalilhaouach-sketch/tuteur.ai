# Installer le tuteur à la maison

Le tuteur tourne sur l'ordinateur de la maison. Les téléphones des enfants s'y connectent par le Wi-Fi.
L'ordinateur doit rester allumé pendant les séances.

> Cette installation est prévue **pour le Wi-Fi de la maison seulement** (protégé par un mot de passe) :
> sans HTTPS, les échanges circulent en clair sur le Wi-Fi. Pour un accès depuis partout, voir la fin du guide.

## 1. Installer Python (une seule fois)

- **Windows** : téléchargez Python (version 3.10 ou plus récente) sur https://www.python.org/downloads/.
  Pendant l'installation, **cochez « Add python.exe to PATH »**.
- **Mac** : téléchargez Python sur https://www.python.org/downloads/ et installez-le.
- **Linux** : Python 3 est en général déjà installé.

Dans les commandes ci-dessous, écrivez `py` sous Windows et `python3` sur Mac et Linux.

## 2. Récupérer le tuteur

Téléchargez le dossier du projet (branche de travail) au format ZIP :
https://github.com/khalilhaouach-sketch/tuteur.ai/archive/refs/heads/claude/awesome-keller-6scbwa.zip

Décompressez-le, par exemple dans `Documents/tuteur`. Ouvrez ensuite un terminal **dans ce dossier** :
- Windows : ouvrez le dossier dans l'Explorateur, cliquez dans la barre d'adresse, tapez `cmd`, puis Entrée ;
- Mac : clic droit sur le dossier › « Nouveau terminal au dossier ».

> Gardez le dépôt GitHub **privé** si vous y ajoutez les leçons des manuels de vos enfants.

## 3. Installer les modules (une seule fois)

```
py -m pip install -r requirements.txt
```

(Mac et Linux : `python3 -m pip install -r requirements.txt`)

## 4. Mettre la clé de l'API Claude (une seule fois)

1. Créez une clé sur https://console.anthropic.com (menu « API Keys »), et ajoutez un moyen de paiement
   (l'utilisation est facturée au volume de texte échangé).
2. Dans le dossier du tuteur, copiez le fichier `.env.exemple` et nommez la copie `.env`.
3. Ouvrez `.env` avec le Bloc-notes et remplacez `collez-votre-cle-ici` par votre clé.

Le fichier `.env` reste sur l'ordinateur : il n'est jamais envoyé sur GitHub. Ne partagez jamais cette clé.

## 5. Lancer le tuteur (à chaque utilisation)

```
py lancer_maison.py
```

(Mac et Linux : `python3 lancer_maison.py`)

La fenêtre affiche deux adresses, par exemple :

```
• Espace parent : http://192.168.1.20:8000/parent
• Page élève    : http://192.168.1.20:8000/
```

Laissez cette fenêtre ouverte pendant les séances. Pour arrêter : `Ctrl+C`.
Au premier lancement, Windows peut demander d'autoriser Python sur le réseau : choisissez **réseau privé** et autorisez.

## 6. Première utilisation

1. Sur votre téléphone, ouvrez l'adresse **Espace parent**, créez votre compte, puis ajoutez vos enfants
   (prénom et niveau : CP ou 1AC).
2. Dans la fiche d'un enfant, touchez **Générer un code**.
3. Sur le téléphone de l'enfant, ouvrez l'adresse **Page élève** et tapez le code. Le téléphone se souvient de
   l'enfant pendant 90 jours.
4. Pour le CP, touchez **🔊 Tester la voix**. Si aucune voix arabe n'est trouvée (Android) :
   Paramètres › Gestion générale › Synthèse vocale › moteur Google › installer la voix « Arabe ».

Astuce : ajoutez la page élève à l'écran d'accueil du téléphone (menu du navigateur › « Ajouter à l'écran d'accueil »).

## Bon à savoir

- **Les données** (comptes, résultats, journaux des séances) sont dans le fichier `data/tuteur.db` du dossier.
  Copiez-le de temps en temps pour en garder une sauvegarde.
- **Mettre à jour le tuteur** : téléchargez à nouveau le ZIP et remplacez les fichiers, **sauf** `.env` et le dossier `data/`.
- **Ajouter vos propres cours** : déposez des fichiers `.docx`, `.md` ou `.txt` dans `docs/cours/`, avec `cp` ou `1ac`
  au début du nom (par exemple `1ac_ma_lecon.docx`), puis relancez le tuteur.
- **Vérifier la qualité du tuteur avec la vraie API** (payant, quelques centimes) :
  `py -m evals.run_evals --reel --profil P1`, puis `--profil P2`.

## Plus tard : accès depuis partout

Pour que les enfants puissent travailler même quand l'ordinateur est éteint, ou hors de la maison, le tuteur peut
être installé sur un petit serveur en ligne, en HTTPS (quelques euros par mois). Le HTTPS sera aussi nécessaire si
l'on ajoute un jour la reconnaissance vocale (le micro).
