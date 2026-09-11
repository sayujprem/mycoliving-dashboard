"""Autoriza a MyColiving a enviar correo por la API de Gmail y genera GMAIL_OAUTH.

Se corre una vez, en tu Mac, con el archivo del cliente OAuth que descargaste de
Google Cloud (Google Auth Platform -> Clientes -> descargar JSON):

    .venv/bin/python -m scripts.autorizar_gmail --credenciales ~/Downloads/client_secret_XXXX.json

Que hace:
1. Abre el navegador para que la cuenta remitente autorice el permiso gmail.send
   (solo enviar: no puede leer, borrar ni ver el correo).
2. Recibe la respuesta de Google en un servidor temporal en 127.0.0.1, que se cierra
   al terminar. Usa PKCE, asi que un codigo interceptado no le sirve a nadie mas.
3. Cambia la respuesta por un refresh token y envia un correo de prueba real a la
   cuenta remitente, por el mismo camino que usa la aplicacion en produccion.
4. Deja GMAIL_OAUTH en el portapapeles para pegarlo en Vercel. No lo imprime.

Volver a correrlo invalida el permiso anterior: hay que actualizar GMAIL_OAUTH en Vercel.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ALCANCE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CUENTA = "privacidad.mycoliving@gmail.com"
ESPERA_MAXIMA = 300  # segundos para completar la autorizacion en el navegador


def pkce() -> tuple[str, str]:
    """Devuelve (verificador, reto). El reto viaja en la URL; el verificador solo al
    canjear el codigo, asi que quien intercepte el codigo no puede usarlo."""
    verificador = secrets.token_urlsafe(64)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, reto


def url_autorizacion(client_id: str, redirect_uri: str, reto: str, estado: str,
                     cuenta: str = CUENTA) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ALCANCE,
        # offline + consent: sin esto Google no entrega el refresh token.
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": reto,
        "code_challenge_method": "S256",
        "state": estado,
        "login_hint": cuenta,
    })


def leer_cliente(ruta: Path) -> dict:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"No pude leer {ruta}: {exc}")
    if "installed" not in datos:
        raise SystemExit(
            "Ese archivo no es de un cliente de tipo 'App de escritorio'. En Google Auth "
            "Platform -> Clientes, crea uno de ese tipo y descarga su JSON."
        )
    cliente = datos["installed"]
    if not cliente.get("client_id") or not cliente.get("client_secret"):
        raise SystemExit("Al archivo le falta client_id o client_secret.")
    return cliente


def _preparar_servidor() -> tuple[http.server.HTTPServer, dict]:
    resultado: dict = {}

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in consulta or "error" in consulta:
                resultado.update({k: v[0] for k, v in consulta.items()})
            if "code" in consulta:
                texto = "Listo. Ya puedes cerrar esta pestaña y volver a la Terminal."
            elif "error" in consulta:
                texto = "Google no autorizó el acceso. Vuelve a la Terminal."
            else:
                texto = ""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<p style='font-family:system-ui;padding:2rem'>{texto}</p>".encode())

        def log_message(self, *args):  # silencio: la URL trae el codigo
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manejador)
    servidor.timeout = 5
    return servidor, resultado


def _canjear(cliente: dict, codigo: str, verificador: str, redirect_uri: str) -> dict:
    datos = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": codigo,
        "code_verifier": verificador,
        "client_id": cliente["client_id"],
        "client_secret": cliente["client_secret"],
        "redirect_uri": redirect_uri,
    }).encode()
    peticion = urllib.request.Request(TOKEN_URL, data=datos, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            return json.loads(respuesta.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Google rechazó el canje del código ({exc.code}): {exc.read()[:200].decode(errors='replace')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera GMAIL_OAUTH para MyColiving.")
    parser.add_argument("--credenciales", required=True, type=Path,
                        help="JSON del cliente OAuth descargado de Google Cloud")
    args = parser.parse_args()

    cliente = leer_cliente(args.credenciales.expanduser())
    verificador, reto = pkce()
    estado = secrets.token_urlsafe(16)
    servidor, resultado = _preparar_servidor()
    redirect_uri = f"http://127.0.0.1:{servidor.server_port}"
    url = url_autorizacion(cliente["client_id"], redirect_uri, reto, estado)

    print(f"Se abre el navegador. Elige la cuenta {CUENTA} y autoriza el permiso.")
    print("Si Google avisa que la app no está verificada: 'Configuración avanzada' ->")
    print("'Ir a MyColiving'. Es tu propia app y el permiso solo permite enviar correo.\n")
    print(f"Si el navegador no se abre, copia esta dirección:\n{url}\n")
    webbrowser.open(url)

    limite = time.time() + ESPERA_MAXIMA
    while not resultado and time.time() < limite:
        servidor.handle_request()
    servidor.server_close()

    if not resultado:
        print("Se agotó la espera sin respuesta de Google. Vuelve a correr el script.")
        return 1
    if "error" in resultado:
        print(f"Google devolvió un error: {resultado['error']}. No se generó nada.")
        return 1
    if resultado.get("state") != estado:
        print("La respuesta no corresponde a esta autorización (state distinto). Se descarta.")
        return 1

    tokens = _canjear(cliente, resultado["code"], verificador, redirect_uri)
    refresh = tokens.get("refresh_token")
    if not refresh:
        print("Google no entregó un refresh token. Quita el acceso de MyColiving en "
              "myaccount.google.com/connections y vuelve a correr el script.")
        return 1

    gmail_oauth = json.dumps(
        {"client_id": cliente["client_id"], "client_secret": cliente["client_secret"],
         "refresh_token": refresh},
        separators=(",", ":"),
    )

    # Prueba real por el mismo codigo que usa la aplicacion. config exige estas dos
    # variables al importarse; aca no se usan, asi que basta con un valor cualquiera.
    os.environ["GMAIL_OAUTH"] = gmail_oauth
    os.environ.setdefault("DATABASE_URL", "postgresql://no-se-usa")
    os.environ.setdefault("SESSION_SECRET", "no-se-usa")
    from web import correo

    enviado = correo._enviar(
        CUENTA,
        "Prueba de envío por la API de Gmail · MyColiving",
        "Este correo confirma que MyColiving puede enviar desde esta cuenta con el permiso nuevo.",
    )
    if not enviado:
        print("El permiso se generó, pero el correo de prueba no salió. Revisa el mensaje de arriba.")
        return 1

    subprocess.run(["pbcopy"], input=gmail_oauth, text=True, check=True)
    print(f"Correo de prueba enviado a {CUENTA}.")
    print(f"GMAIL_OAUTH quedó en el portapapeles ({len(gmail_oauth)} caracteres). Pégalo en Vercel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
