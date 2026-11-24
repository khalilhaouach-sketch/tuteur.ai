# Image du tuteur (API + pages élève et parent). Construite par compose.yml à la racine du projet.
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# La base SQLite vit dans un volume (/data), pour survivre aux mises à jour de l'image.
ENV TUTEUR_DB=/data/tuteur.db \
    TUTEUR_COOKIE_SECURE=1 \
    PYTHONUNBUFFERED=1
RUN useradd --create-home tuteur && mkdir -p /data && chown tuteur /data
USER tuteur

EXPOSE 8000
# --proxy-headers : derrière Caddy, l'adresse IP réelle du visiteur sert à limiter les essais de connexion.
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
