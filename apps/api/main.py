"""Point d'entrée de l'API : uvicorn apps.api.main:app"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api import db
from apps.api.auth.routes import router as auth_router


@asynccontextmanager
async def demarrage(_app: FastAPI):
    db.initialiser()
    yield


def creer_app() -> FastAPI:
    app = FastAPI(title="Tuteur IA — API", lifespan=demarrage)
    app.include_router(auth_router)
    return app


app = creer_app()
