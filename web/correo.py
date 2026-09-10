"""Envio de correo transaccional con Resend.

Llamada HTTP directa con httpx, que ya es dependencia del proyecto. No se agrega el
SDK de Resend: son dos peticiones POST y no justifica una dependencia mas en el
paquete que se despliega.

Ningun fallo de correo tumba la operacion que lo disparo. Si el envio falla, la cuenta
queda creada y el usuario puede pedir otro enlace; devolver un error 500 en mitad del
alta seria peor.
"""
import logging

import httpx

from config import APP_URL, RESEND_API_KEY, RESEND_REMITENTE

log = logging.getLogger(__name__)

_URL = "https://api.resend.com/emails"
_TIMEOUT = 10.0


def _enviar(destino: str, asunto: str, cuerpo: str) -> bool:
    if not RESEND_API_KEY:
        # En desarrollo y en los tests no hay clave: el enlace se imprime en el log
        # para poder seguir el flujo sin montar un servidor de correo.
        log.warning("Sin RESEND_API_KEY. Correo para %s no enviado:\n%s", destino, cuerpo)
        return False
    try:
        respuesta = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_REMITENTE,
                "to": [destino],
                "subject": asunto,
                "text": cuerpo,
            },
            timeout=_TIMEOUT,
        )
        if respuesta.status_code >= 400:
            log.error("Resend respondio %s: %s", respuesta.status_code, respuesta.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
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
        "Si no creaste esta cuenta, ignora este mensaje: no se hara nada.",
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
