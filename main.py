"""Punto de entrada de la aplicación. Levantar con: uvicorn main:app --reload"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.routes import router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="MyColiving Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
app.include_router(router)
