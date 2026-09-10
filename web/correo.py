"""Envio de correo transaccional por el SMTP de Gmail.

Se usa la biblioteca estandar (smtplib), sin servicios ni dependencias adicionales.
La cuenta que envia es la de contacto de privacidad; Gmail permite unos 500
destinatarios al dia desde una cuenta personal, que sobra para verificaciones y
recuperaciones de contrasena.

Ningun fallo de correo tumba la operacion que lo disparo. Si el envio falla, la cuenta
queda creada y el usuario puede pedir otro enlace; devolver un error 500 en mitad del
alta seria peor.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from config import APP_URL, SMTP_CLAVE, SMTP_USUARIO

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PUERTO = 587  # STARTTLS: la conexion arranca en claro y se cifra antes del login
_TIMEOUT = 10.0


def _enviar(destino: str, asunto: str, cuerpo: str) -> bool:
    if not SMTP_CLAVE:
        # En desarrollo y en los tests no hay clave: el enlace se imprime en el log
        # para poder seguir el flujo sin enviar correos de verdad.
        log.warning("Sin SMTP_CLAVE. Correo para %s no enviado:\n%s", destino, cuerpo)
        return False

    mensaje = EmailMessage()
    try:
        mensaje["From"] = formataddr(("MyColiving", SMTP_USUARIO))
        # EmailMessage rechaza saltos de linea en las cabeceras, lo que cierra la
        # inyeccion de cabeceras por el campo del correo. El alta ya valida el formato.
        mensaje["To"] = destino
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo)
    except ValueError as exc:
        log.error("Destinatario o cabecera invalida (%r): %s", destino, exc)
        return False

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PUERTO, timeout=_TIMEOUT) as servidor:
            # Sin un contexto que valide el certificado, un tercero en la red podria
            # hacerse pasar por Gmail y quedarse con la contrasena de aplicacion.
            servidor.starttls(context=ssl.create_default_context())
            servidor.login(SMTP_USUARIO, SMTP_CLAVE)
            servidor.send_message(mensaje)
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail rechazo las credenciales de %s. Revisa SMTP_CLAVE.", SMTP_USUARIO)
        return False
    except (smtplib.SMTPException, OSError) as exc:
        log.error("No se pudo enviar el correo a %s: %s", destino, exc)
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
