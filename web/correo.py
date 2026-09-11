"""Envio de correo transaccional por la API de Gmail.

La aplicacion envia desde CORREO_REMITENTE con un permiso OAuth (GMAIL_OAUTH) y no con
usuario y contrasena. La primera version usaba SMTP con contrasena de aplicacion, y
Google bloqueo la cuenta con "Please log in with your web browser" en cuanto Vercel
intento enviar: una cuenta nueva que inicia sesion desde un centro de datos parece un
acceso robado. Una llamada a la API con un permiso OAuth no es un inicio de sesion y no
pasa por ese filtro.

Cada envio hace hasta dos peticiones HTTPS con la biblioteca estandar, sin dependencias:
una para cambiar el permiso de larga duracion (refresh token) por una credencial de una
hora, que se guarda en memoria mientras la instancia de Vercel siga viva, y otra para
enviar el mensaje.

Ningun fallo de correo tumba la operacion que lo disparo. Si el envio falla, la cuenta
queda creada y el usuario puede pedir otro enlace; devolver un error 500 en mitad del
alta seria peor.
"""
import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from config import APP_URL, CORREO_REMITENTE, GMAIL_OAUTH

log = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
ENVIO_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_TIMEOUT = 10

# Punto de inyeccion para las pruebas: reemplazan esta funcion por un servidor falso.
_abrir = urllib.request.urlopen

# Credencial de acceso vigente. Dura una hora; se renueva un minuto antes de vencer.
_cache: dict = {"token": None, "vence": 0.0}


class PermisoRevocado(Exception):
    """El refresh token dejo de servir: se revoco, o la cuenta cambio su contrasena."""


def _credenciales() -> dict | None:
    if not GMAIL_OAUTH:
        return None
    try:
        datos = json.loads(GMAIL_OAUTH)
    except ValueError:
        log.error("GMAIL_OAUTH no es un JSON valido. Vuelve a generarlo con scripts/autorizar_gmail.py.")
        return None
    if not all(datos.get(k) for k in ("client_id", "client_secret", "refresh_token")):
        log.error("A GMAIL_OAUTH le falta client_id, client_secret o refresh_token.")
        return None
    return datos


def _post(url: str, *, formulario: dict | None = None, cuerpo_json: dict | None = None,
          token: str | None = None) -> dict:
    if formulario is not None:
        datos = urllib.parse.urlencode(formulario).encode()
        tipo = "application/x-www-form-urlencoded"
    else:
        datos = json.dumps(cuerpo_json).encode()
        tipo = "application/json"
    peticion = urllib.request.Request(url, data=datos, method="POST", headers={"Content-Type": tipo})
    if token:
        peticion.add_header("Authorization", f"Bearer {token}")
    with _abrir(peticion, timeout=_TIMEOUT) as respuesta:
        return json.loads(respuesta.read() or b"{}")


def _token_de_acceso(cred: dict) -> str:
    if _cache["token"] and time.time() < _cache["vence"] - 60:
        return _cache["token"]
    try:
        respuesta = _post(TOKEN_URL, formulario={
            "grant_type": "refresh_token",
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "refresh_token": cred["refresh_token"],
        })
    except urllib.error.HTTPError as exc:
        detalle = exc.read()[:300].decode(errors="replace")
        if "invalid_grant" in detalle:
            raise PermisoRevocado() from exc
        raise
    _cache["token"] = respuesta["access_token"]
    _cache["vence"] = time.time() + int(respuesta.get("expires_in", 3600))
    return _cache["token"]


def _enviar(destino: str, asunto: str, cuerpo: str) -> bool:
    cred = _credenciales()
    if not cred:
        # En desarrollo y en los tests no hay permiso: el enlace se imprime en el log
        # para poder seguir el flujo sin enviar correos de verdad.
        log.warning("Sin GMAIL_OAUTH. Correo para %s no enviado:\n%s", destino, cuerpo)
        return False

    mensaje = EmailMessage()
    try:
        mensaje["From"] = formataddr(("MyColiving", CORREO_REMITENTE))
        # EmailMessage rechaza saltos de linea en las cabeceras, lo que cierra la
        # inyeccion de cabeceras por el campo del correo. El alta ya valida el formato.
        mensaje["To"] = destino
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo)
    except ValueError as exc:
        log.error("Destinatario o cabecera invalida (%r): %s", destino, exc)
        return False
    crudo = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()

    # Dos intentos: si la credencial en memoria vencio antes de lo previsto, Gmail
    # responde 401; se descarta y se pide una nueva una sola vez.
    for intento in (1, 2):
        try:
            _post(ENVIO_URL, cuerpo_json={"raw": crudo}, token=_token_de_acceso(cred))
            return True
        except PermisoRevocado:
            log.error(
                "Google rechazo el permiso de Gmail (invalid_grant): se revoco o la cuenta "
                "cambio su contrasena. Vuelve a correr scripts/autorizar_gmail.py y "
                "actualiza GMAIL_OAUTH."
            )
            return False
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and intento == 1:
                _cache["token"] = None
                continue
            detalle = exc.read()[:300].decode(errors="replace")
            log.error("La API de Gmail respondio %s: %s", exc.code, detalle)
            return False
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            log.error("No se pudo enviar el correo a %s: %s", destino, exc)
            return False
    return False


def enviar_verificacion(destino: str, token: str) -> bool:
    enlace = f"{APP_URL}/verificar/{token}"
    return _enviar(
        destino,
        "Confirma tu correo en MyColiving",
        "Para activar tu cuenta, abre este enlace:\n\n"
        f"{enlace}\n\n"
        "El enlace vence en 24 horas.\n"
        "Si no creaste esta cuenta, ignora este mensaje: no se hará nada.",
    )


def enviar_recuperacion(destino: str, token: str) -> bool:
    enlace = f"{APP_URL}/recuperar/{token}"
    return _enviar(
        destino,
        "Restablece tu contraseña de MyColiving",
        "Para elegir una contraseña nueva, abre este enlace:\n\n"
        f"{enlace}\n\n"
        "El enlace vence en 1 hora y solo sirve una vez.\n"
        "Si no lo pediste, ignora este mensaje: tu contraseña sigue igual.",
    )
