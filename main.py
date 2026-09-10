"""Punto de entrada de la aplicación. Levantar con: uvicorn main:app --reload

En Vercel no hace falta configurar nada: el runtime de Python detecta FastAPI y toma
la variable `app` de este archivo como punto de entrada.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import ES_PRODUCCION, SESSION_COOKIE, SESSION_MAX_AGE, SESSION_SECRET
from web.auth import CSRFMiddleware, Redirigir
from web.routes import router
from web.seguridad import CabecerasSeguridad

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="MyColiving Dashboard", docs_url=None, redoc_url=None)

# El orden importa y no es el que se lee. Starlette ejecuta el ultimo middleware
# agregado como el mas externo, asi que esta lista corre de abajo hacia arriba:
# cabeceras -> sesion -> CSRF -> rutas.
#
# CSRF tiene que quedar por dentro de la sesion porque necesita leer el token que
# guarda la cookie. Si se invierten, el token siempre llega vacio y ningun formulario
# funciona.
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=SESSION_COOKIE,
    max_age=SESSION_MAX_AGE,
    same_site="lax",   # el navegador no envia la cookie en peticiones de otros sitios
    https_only=ES_PRODUCCION,
    # httponly viene activado por defecto: JavaScript no puede leer la cookie.
)
app.add_middleware(CabecerasSeguridad)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")
app.include_router(router)


@app.exception_handler(Redirigir)
async def _redirigir(request: Request, exc: Redirigir) -> RedirectResponse:
    """Traduce la senal que lanzan las dependencias de sesion a una redireccion."""
    return RedirectResponse(exc.destino, status_code=303)
