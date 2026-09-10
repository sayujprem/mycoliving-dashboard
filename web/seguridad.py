"""Cabeceras de seguridad HTTP.

Son instrucciones al navegador sobre que le esta permitido hacer con la pagina. No
cuestan nada y cierran clases enteras de ataque: robo de la sesion desde un iframe,
ejecucion de scripts inyectados, filtracion de la URL hacia sitios de terceros.
"""
from starlette.middleware.base import BaseHTTPMiddleware

from config import ES_PRODUCCION

# La aplicacion no carga JavaScript de terceros ni usa scripts en linea. La unica
# excepcion son las tipografias de Google, que base.html ya trae. Todo lo demas queda
# prohibido: si alguien logra inyectar una etiqueta <script>, el navegador no la ejecuta.
_CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' https://fonts.googleapis.com",
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
