"""Utilidades compartidas por las pruebas.

Con autenticacion, cada prueba de rutas necesita un usuario verificado, una sesion
iniciada y el token CSRF en cada POST. Este modulo lo resuelve una vez para que las
pruebas sigan diciendo lo que prueban y no como se entra.
"""
import base64
import json

from fastapi.testclient import TestClient

from config import SESSION_COOKIE
from db.connection import fijar_usuario
from db.repositorio import get_activo
from db.usuarios import (
    crear_usuario,
    get_usuario_por_email,
    marcar_email_verificado,
    set_asesoria_habilitada,
)

EMAIL_PRUEBA = "prueba@ejemplo.com"
PASSWORD_PRUEBA = "clave-de-prueba-larga"

_usuario_en_curso: dict = {}


class ClienteConSesion(TestClient):
    """TestClient que agrega el token CSRF de la sesion a todo POST.

    El token vive dentro de la cookie de sesion. La cookie va firmada, no cifrada: el
    primer tramo es el JSON de la sesion en base64, asi que se puede leer sin la clave.
    """

    def _csrf(self) -> str | None:
        crudo = self.cookies.get(SESSION_COOKIE)
        if not crudo:
            return None
        carga = crudo.split(".")[0]
        carga += "=" * (-len(carga) % 4)
        return json.loads(base64.b64decode(carga)).get("csrf")

    def request(self, method, url, *args, **kwargs):
        if method.upper() == "POST":
            data = dict(kwargs.get("data") or {})
            if "csrf_token" not in data:
                if not self._csrf():
                    super().request("GET", "/entrar")  # crea la sesion con su token
                data["csrf_token"] = self._csrf()
            kwargs["data"] = data
        return super().request(method, url, *args, **kwargs)


def asegurar_usuario(email: str = EMAIL_PRUEBA, *, asesoria: bool = False) -> dict:
    """Crea (si hace falta) una cuenta verificada y la deja como duena del contexto.

    Fijarla importa para las pruebas que llaman al repositorio o al dominio directo,
    sin pasar por una ruta: las politicas de aislamiento de la base tambien aplican
    ahi, y sin usuario fijado no se ve ni se escribe nada.
    """
    usuario = get_usuario_por_email(email)
    if not usuario:
        crear_usuario(email, PASSWORD_PRUEBA)
        usuario = get_usuario_por_email(email)
    marcar_email_verificado(usuario["id"])
    set_asesoria_habilitada(usuario["id"], asesoria)
    usuario = get_usuario_por_email(email)
    fijar_usuario(usuario["id"])
    _usuario_en_curso.clear()
    _usuario_en_curso.update(usuario)
    return usuario


def nuevo_cliente(email: str = EMAIL_PRUEBA, *, asesoria: bool = False) -> ClienteConSesion:
    """Cliente HTTP con la sesion de una cuenta verificada ya iniciada."""
    from main import app

    asegurar_usuario(email, asesoria=asesoria)
    cliente = ClienteConSesion(app)
    cliente.post("/entrar", data={"email": email, "password": PASSWORD_PRUEBA})
    # El login ocurre en otro hilo; se vuelve a fijar la cuenta en el de la prueba.
    fijar_usuario(_usuario_en_curso["id"])
    return cliente


def activo_actual() -> dict | None:
    """El activo de la cuenta de prueba en curso. Reemplaza al get_activo() global."""
    return get_activo(_usuario_en_curso["id"])


def usuario_actual_id() -> int:
    return _usuario_en_curso["id"]
