"""Point d'entrée de l'API : uvicorn apps.api.main:app"""

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from apps.api import db
from apps.api.auth.routes import router as auth_router
from apps.api.sessions.routes import router as seances_router

PAGE_ELEVE = Path(__file__).resolve().parents[1] / "web" / "student" / "index.html"


@asynccontextmanager
async def demarrage(_app: FastAPI):
    db.initialiser()
    yield


def creer_app() -> FastAPI:
    app = FastAPI(title="Tuteur IA — API", lifespan=demarrage)
    app.include_router(auth_router)
    app.include_router(seances_router)

    @app.get("/", include_in_schema=False)
    def page_eleve():
        return FileResponse(PAGE_ELEVE)

    return app


app = creer_app()
