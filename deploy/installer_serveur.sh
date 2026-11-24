#!/usr/bin/env bash
# Installe et démarre le tuteur sur un serveur Ubuntu (22.04 ou 24.04), en HTTPS.
# À lancer depuis le dossier du tuteur, sur le serveur :  sudo bash deploy/installer_serveur.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(id -u)" -ne 0 ]; then echo "Lancez ce script avec sudo."; exit 1; fi

echo "== 1/4 Installation de Docker"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -y -q docker.io docker-compose-v2
fi
systemctl enable --now docker

echo "== 2/4 Pare-feu : SSH, HTTP et HTTPS seulement"
if command -v ufw >/dev/null; then
  ufw allow OpenSSH >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
fi

echo "== 3/4 Réglages (fichier .env)"
if [ ! -f .env ]; then
  read -r -p "Nom de domaine du tuteur (ex. tuteur.mondomaine.ma) : " DOMAINE
  read -r -s -p "Clé API Claude (elle ne s'affiche pas) : " CLE; echo
  umask 077
  printf 'DOMAINE=%s\nANTHROPIC_API_KEY=%s\n' "$DOMAINE" "$CLE" > .env
  echo "   .env créé (lisible seulement par l'administrateur)."
else
  echo "   .env existe déjà : conservé."
fi
DOMAINE=$(grep -E '^DOMAINE=' .env | cut -d= -f2-)
if [ -z "$DOMAINE" ]; then echo "DOMAINE manque dans .env."; exit 1; fi

echo "== 4/4 Construction et démarrage (quelques minutes la première fois)"
docker compose up -d --build

echo
echo "Terminé. Dans une minute (le temps d'obtenir le certificat HTTPS), ouvrez :"
echo "  Espace parent : https://$DOMAINE/parent"
echo "  Page élève    : https://$DOMAINE/"
echo "Si la page ne s'ouvre pas : vérifiez que le domaine pointe bien vers ce serveur (enregistrement A)."
