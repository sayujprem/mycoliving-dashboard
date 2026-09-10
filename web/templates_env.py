"""Entorno Jinja2 compartido por todas las rutas."""
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from web.auth import token_csrf

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _contexto_sesion(request: Request) -> dict:
    """Variables que toda plantilla necesita y ninguna ruta deberia tener que pasar.

    `csrf_token` lo exige cada formulario POST (lo valida web/auth.CSRFMiddleware).
    `usuario_sesion` alimenta el menu de cuenta del encabezado; lo deja en
    request.state la dependencia de sesion, asi que no cuesta otra consulta.
    """
    return {
        "csrf_token": token_csrf(request),
        "usuario_sesion": getattr(request.state, "usuario", None),
    }


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_contexto_sesion])
