"""Point d'entrée de l'API : uvicorn apps.api.main:app"""

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from apps.api.config import charger_env

charger_env()  # .env local (clé API...), avant tout le reste

from apps.api import db  # noqa: E402
from rag.ingest import indexer  # noqa: E402
from apps.api.auth.routes import router as auth_router
from apps.api.parcours.routes import router as parcours_router
from apps.api.reports.routes import router as parent_router
from apps.api.sessions.routes import router as seances_router

WEB = Path(__file__).resolve().parents[1] / "web"
PAGE_ELEVE = WEB / "student" / "index.html"
PAGE_PARENT = WEB / "parent" / "index.html"


@asynccontextmanager
async def demarrage(_app: FastAPI):
    db.initialiser()
    conn = db.ouvrir()
    try:
        indexer(conn)  # docs/ est réindexé à chaque démarrage : l'index suit toujours les fichiers
        conn.commit()
    finally:
        conn.close()
    yield


def creer_app() -> FastAPI:
    app = FastAPI(title="Tuteur IA — API", lifespan=demarrage)
    app.include_router(auth_router)
    app.include_router(seances_router)
    app.include_router(parent_router)
    app.include_router(parcours_router)

    @app.get("/", include_in_schema=False)
    def page_eleve():
        return FileResponse(PAGE_ELEVE)

    @app.get("/parent", include_in_schema=False)
    def page_parent():
        return FileResponse(PAGE_PARENT)

    return app


app = creer_app()
