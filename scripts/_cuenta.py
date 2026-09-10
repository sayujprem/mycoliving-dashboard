"""Resolucion de cuenta para los scripts de consola.

Con varias cuentas, "el activo" ya no existe: cada script tiene que decir de quien
habla. Ademas, las politicas de aislamiento de la base se aplican tambien aca: un
script que no fije la cuenta no ve ni escribe nada. Es una garantia, no un estorbo.
"""
import sys

from db.connection import fijar_usuario
from db.repositorio import get_activo
from db.usuarios import get_usuario_por_email


def email_de_argumentos() -> str | None:
    """Lee `--email correo@dominio` de la linea de comandos."""
    args = sys.argv[1:]
    if "--email" in args:
        i = args.index("--email")
        if i + 1 < len(args):
            return args[i + 1]
    return None


def abrir_cuenta(email: str | None) -> tuple[dict, dict | None] | None:
    """Devuelve (usuario, activo) y deja la cuenta fijada para las consultas siguientes."""
    if not email:
        print("Falta la cuenta. Agrega: --email correo@dominio")
        return None
    usuario = get_usuario_por_email(email)
    if not usuario:
        print(f"No hay ninguna cuenta con el correo {email}.")
        return None
    fijar_usuario(usuario["id"])
    return usuario, get_activo(usuario["id"])
