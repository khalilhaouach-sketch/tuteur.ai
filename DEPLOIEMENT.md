# Mettre le tuteur en ligne (serveur + nom de domaine, en HTTPS)

Le tuteur tourne sur un petit serveur loué, toujours allumé. Les enfants l'ouvrent depuis n'importe où, à une
adresse comme `https://tuteur.mondomaine.ma`. Le certificat HTTPS est obtenu et renouvelé automatiquement.

Ce qu'il faut : un nom de domaine (vous l'avez), un petit serveur, votre clé API Claude, et votre Mac pour les
commandes. Comptez une demi-heure la première fois.

## 1. Louer un serveur (une seule fois)

Un « VPS » sous **Ubuntu 24.04** suffit : 2 Go de mémoire, 1 ou 2 processeurs. Fournisseurs possibles :
Hetzner, OVHcloud, DigitalOcean, Contabo (quelques euros par mois ; vérifiez le prix sur leur site).

À la création, choisissez :
- système : **Ubuntu 24.04** ;
- accès : **clé SSH** si on vous la propose (plus sûr qu'un mot de passe ; sinon, un mot de passe long) ;
- région : Europe (le plus proche du Maroc).

Notez l'**adresse IP** du serveur (par exemple `203.0.113.10`).

## 2. Faire pointer le domaine vers le serveur

Chez le fournisseur de votre nom de domaine (rubrique « DNS » ou « Zone DNS »), ajoutez un enregistrement :

| Type | Nom | Valeur |
| --- | --- | --- |
| A | `tuteur` | l'adresse IP du serveur |

L'adresse du tuteur sera alors `tuteur.mondomaine.ma` (avec votre domaine). La prise en compte prend de
quelques minutes à quelques heures. Pour vérifier, dans le Terminal du Mac :

```
ping tuteur.mondomaine.ma
```

doit afficher l'adresse IP du serveur (`Ctrl + C` pour arrêter).

## 3. Envoyer le tuteur sur le serveur

Dans le Terminal du Mac (remplacez l'adresse IP) :

```
scp -r ~/Documents/tuteur root@203.0.113.10:/opt/tuteur
```

(Si votre fournisseur vous donne un autre utilisateur qu'`root`, par exemple `ubuntu`, utilisez-le à la place.)

## 4. Installer et démarrer

Connectez-vous au serveur :

```
ssh root@203.0.113.10
```

puis :

```
cd /opt/tuteur
sudo bash deploy/installer_serveur.sh
```

Le script :
1. installe Docker ;
2. ferme tous les accès sauf SSH, HTTP et HTTPS ;
3. vous demande le **nom de domaine** et votre **clé API** (elle ne s'affiche pas quand vous la tapez ; elle est
   enregistrée dans `/opt/tuteur/.env`, lisible seulement par l'administrateur) ;
4. construit et démarre le tuteur et Caddy (qui gère le HTTPS).

Au bout d'une minute, ouvrez `https://tuteur.mondomaine.ma/parent`.

## 5. Fermer les inscriptions (important)

Le tuteur est public : n'importe qui trouvant l'adresse pourrait créer un compte et utiliser vos crédits API.
Dès que **votre** compte parent est créé, fermez les inscriptions, sur le serveur :

```
cd /opt/tuteur && echo TUTEUR_INSCRIPTIONS=0 >> .env && docker compose up -d
```

Vous pouvez toujours vous connecter, ajouter des enfants et générer des codes. Pour rouvrir :
retirez la ligne `TUTEUR_INSCRIPTIONS=0` de `.env` (`nano .env`), puis `docker compose up -d`.

## Au quotidien

Il n'y a rien à faire : le tuteur redémarre tout seul si le serveur redémarre.

**Mettre à jour le tuteur** (nouvelle version publiée sur GitHub), sur le serveur :

```
cd /opt/tuteur && bash deploy/mettre_a_jour.sh
```

Le fichier `.env` et les données des enfants sont conservés.

**Sauvegarder les données** (comptes, résultats, journaux), sur le serveur :

```
cd /opt/tuteur && sudo docker compose cp tuteur:/data/tuteur.db ./sauvegarde-$(date +%F).db
```

puis, depuis le Mac, rapatriez la copie :

```
scp root@203.0.113.10:/opt/tuteur/sauvegarde-*.db ~/Documents/
```

**Voir ce qui se passe** (en cas de problème) : `cd /opt/tuteur && sudo docker compose logs --tail 50`

## Sécurité

- Seuls les ports SSH (22), HTTP (80) et HTTPS (443) sont ouverts ; le tuteur lui-même n'est joignable que par Caddy.
- La clé API reste sur le serveur, dans `.env` : elle n'est jamais envoyée aux téléphones ni sur GitHub.
- Les cookies de connexion ne circulent qu'en HTTPS.
- Pensez à mettre à jour Ubuntu de temps en temps : `sudo apt update && sudo apt upgrade -y`.
