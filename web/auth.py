"""Sesion, proteccion CSRF y resolucion del activo de cada peticion.

La sesion vive en una cookie firmada (SessionMiddleware de Starlette). Dentro solo van
dos numeros: el id del usuario y la version de su sesion. Ningun dato personal viaja al
navegador, la firma impide falsificarla, y la version permite cerrarla desde el
servidor cuando el usuario cambia su contrasena.

Las rutas no leen la cookie a mano: piden `requiere_sesion` o `requiere_activo` como
dependencia. Esas dos funciones son ademas las unicas que declaran, en la variable de
contexto que lee db/connection.py, de quien son los datos que la peticion puede tocar.
"""
import secrets
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse

from db.connection import fijar_usuario
from db.repositorio import get_activo
from db.usuarios import get_usuario

CLAVE_CSRF = "csrf"
CAMPO_CSRF = "csrf_token"


class Redirigir(Exception):
    """Corta la peticion y manda al usuario a otra ruta.

    Existe para que las dependencias puedan redirigir sin que cada ruta tenga que
    comprobar si lo que recibio es un usuario o una respuesta. main.py la traduce a
    una respuesta 303.
    """

    def __init__(self, destino: str):
        self.destino = destino


# --- sesion ------------------------------------------------------------------


def iniciar_sesion(request: Request, usuario: dict) -> None:
    request.session.clear()
    request.session["uid"] = usuario["id"]
    request.session["v"] = usuario["token_sesion"]
    request.session[CLAVE_CSRF] = secrets.token_urlsafe(32)
    fijar_usuario(usuario["id"])


def cerrar_sesion(request: Request) -> None:
    request.session.clear()
    fijar_usuario(None)


def usuario_actual(request: Request) -> dict | None:
    """Resuelve el usuario de la peticion, o None si no hay sesion valida.

    Comprobar `token_sesion` contra la base en cada peticion es lo que hace que un
    cambio de contrasena cierre las sesiones abiertas de inmediato, en vez de dejarlas
    vivas hasta que caduque la cookie.
    """
    uid = request.session.get("uid")
    if not uid:
        fijar_usuario(None)
        return None

    usuario = get_usuario(uid)
    if not usuario or usuario["token_sesion"] != request.session.get("v"):
        request.session.clear()
        fijar_usuario(None)
        return None

    fijar_usuario(usuario["id"])
    return usuario


def requiere_sesion(request: Request) -> dict:
    usuario = usuario_actual(request)
    if not usuario:
        raise Redirigir("/entrar")
    if not usuario["email_verificado_en"]:
        raise Redirigir("/verificar-aviso")
    return usuario


def requiere_admin(request: Request) -> dict:
    usuario = requiere_sesion(request)
    if not usuario["es_admin"]:
        # Se devuelve al panel sin explicar nada: quien no es administrador no tiene
        # por que enterarse de que esta ruta existe.
        raise Redirigir("/")
    return usuario


def requiere_activo(request: Request) -> tuple[dict, dict]:
    """Devuelve (usuario, activo). Si la cuenta aun no configuro su activo, redirige.

    Reemplaza al `activo = get_activo()` que abria cada ruta cuando la aplicacion era
    de un solo usuario. El activo sale de la sesion; nunca de un parametro del cliente.
    """
    usuario = requiere_sesion(request)
    activo = get_activo(usuario["id"])
    if not activo:
        raise Redirigir("/config/activo")
    return usuario, activo


def activo_opcional(request: Request) -> tuple[dict, dict | None]:
    """Como requiere_activo, pero tolera que todavia no haya activo.

    Lo usan el panel, que muestra un estado vacio, y las rutas de borrado, que no
    tienen nada que borrar.
    """
    usuario = requiere_sesion(request)
    return usuario, get_activo(usuario["id"])


# --- CSRF --------------------------------------------------------------------


def token_csrf(request: Request) -> str:
    """Token de la sesion actual. Se crea al vuelo si aun no existe (por ejemplo en el
    formulario de acceso, donde todavia no hay usuario)."""
    token = request.session.get(CLAVE_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CLAVE_CSRF] = token
    return token


class CSRFMiddleware:
    """Rechaza todo POST que no traiga el token de la sesion.

    Se implementa como middleware ASGI y no como dependencia de cada ruta a proposito:
    una dependencia hay que acordarse de poner en cada endpoint nuevo, y basta olvidarla
    una vez. Esto cubre lo que exista hoy y lo que se agregue manana.

    Comprueba tres cosas: que el origen de la peticion sea este mismo sitio, que el
    formulario traiga el token, y que coincida con el de la sesion.

    Lee el cuerpo de la peticion y lo vuelve a poner en circulacion (`replay`), porque
    quien lo consume despues es la ruta.
    """

    METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in self.METODOS_SEGUROS:
            await self.app(scope, receive, send)
            return

        cabeceras = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}

        if not self._mismo_origen(cabeceras):
            await self._rechazar(send, "El origen de la solicitud no coincide.")
            return

        cuerpo = await self._leer_cuerpo(receive)
        enviado = self._token_del_cuerpo(cuerpo, cabeceras)
        esperado = scope.get("session", {}).get(CLAVE_CSRF)

        if not esperado or not enviado or not secrets.compare_digest(enviado, esperado):
            await self._rechazar(send, "Tu sesion expiro. Vuelve a cargar la pagina.")
            return

        await self.app(scope, self._replay(cuerpo), send)

    def _mismo_origen(self, cabeceras: dict) -> bool:
        """El navegador manda Origin en todo POST. Si viene de otro sitio, no es nuestro."""
        origen = cabeceras.get("origin") or cabeceras.get("referer")
        host = cabeceras.get("host")
        if not origen:
            # Sin Origin ni Referer no hay nada que contrastar; el token decide.
            return True
        if not host:
            return False
        return origen.split("://")[-1].split("/")[0] == host

    async def _leer_cuerpo(self, receive) -> bytes:
        partes = []
        while True:
            mensaje = await receive()
            partes.append(mensaje.get("body", b""))
            if not mensaje.get("more_body", False):
                break
        return b"".join(partes)

    def _token_del_cuerpo(self, cuerpo: bytes, cabeceras: dict) -> str | None:
        # Los formularios de la aplicacion son urlencoded. La cabecera es la via
        # alternativa, util si algun dia hay una llamada desde JavaScript.
        if cabeceras.get("x-csrf-token"):
            return cabeceras["x-csrf-token"]
        tipo = cabeceras.get("content-type", "")
        if "application/x-www-form-urlencoded" not in tipo:
            return None
        try:
            campos = parse_qs(cuerpo.decode("utf-8"))
        except UnicodeDecodeError:
            return None
        valores = campos.get(CAMPO_CSRF)
        return valores[0] if valores else None

    def _replay(self, cuerpo: bytes):
        """Devuelve el cuerpo ya leido a quien venga despues."""
        entregado = False

        async def receive():
            nonlocal entregado
            if entregado:
                return {"type": "http.disconnect"}
            entregado = True
            return {"type": "http.request", "body": cuerpo, "more_body": False}

        return receive

    async def _rechazar(self, send, mensaje: str) -> None:
        cuerpo = (
            "<!doctype html><meta charset='utf-8'>"
            f"<p style='font-family:system-ui;padding:2rem'>{mensaje}</p>"
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(cuerpo)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})


def redirigir(destino: str) -> RedirectResponse:
    """Redireccion tras un POST correcto (patron POST-Redirect-GET)."""
    return RedirectResponse(destino, status_code=303)
