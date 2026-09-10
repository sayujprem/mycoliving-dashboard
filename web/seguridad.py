"""Cabeceras de seguridad HTTP.

Son instrucciones al navegador sobre que le esta permitido hacer con la pagina. No
cuestan nada y cierran clases enteras de ataque: robo de la sesion desde un iframe,
ejecucion de scripts inyectados, filtracion de la URL hacia sitios de terceros.
"""
from starlette.middleware.base import BaseHTTPMiddleware

from config import ES_PRODUCCION

# La aplicacion no carga JavaScript de terceros ni usa scripts en linea: el unico
# script es /static/app.js. Si alguien logra inyectar una etiqueta <script> o un
# atributo onclick, el navegador no lo ejecuta.
#
# Los estilos si se permiten en linea ('unsafe-inline'), y es una concesion consciente:
# las plantillas llevan 179 atributos style="..." que forman parte del diseno. Mover
# todos a clases seria reescribir la interfaz para cerrar un riesgo marginal, porque
# con el autoescape de Jinja activo no hay por donde inyectar CSS.
_CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    )
)


class CabecerasSeguridad(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        respuesta = await call_next(request)
        cabeceras = respuesta.headers

        cabeceras["Content-Security-Policy"] = _CSP
        cabeceras["X-Content-Type-Options"] = "nosniff"
        cabeceras["X-Frame-Options"] = "DENY"
        cabeceras["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Ninguna pantalla usa camara, microfono ni ubicacion.
        cabeceras["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if ES_PRODUCCION:
            # Solo en produccion: en local no hay HTTPS y esto dejaria el navegador
            # intentando conectarse por https a 127.0.0.1 durante un ano.
            cabeceras["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return respuesta
