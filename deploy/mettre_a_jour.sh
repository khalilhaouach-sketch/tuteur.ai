#!/usr/bin/env bash
# Met à jour le tuteur sur le serveur avec la dernière version de GitHub, sans toucher aux données ni au .env.
# Sur le serveur :  cd /opt/tuteur && bash deploy/mettre_a_jour.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ZIP=https://github.com/khalilhaouach-sketch/tuteur.ai/archive/refs/heads/claude/awesome-keller-6scbwa.zip
TMP=$(mktemp -d)
curl -sSL -o "$TMP/tuteur.zip" "$ZIP"
unzip -q "$TMP/tuteur.zip" -d "$TMP"
# Copie la nouvelle version par-dessus l'ancienne ; .env (clé, domaine) reste en place.
cp -a "$TMP"/tuteur.ai-*/. .
rm -rf "$TMP"
docker compose up -d --build
echo "Mise à jour terminée."
