"""Rutas de cuenta: acceso, alta, verificacion de correo, recuperacion, perfil y admin.

Ojo con los nombres: en esta aplicacion `/registro` ya es el registro mensual del
informe. Por eso el alta de usuarios vive en `/crear-cuenta` y el acceso en `/entrar`.

Tres criterios atraviesan todo el archivo:

- **No revelar si una cuenta existe.** El alta, el acceso y la recuperacion responden
  igual exista o no el correo. Si no, cualquiera podria usar estos formularios para
  averiguar quien tiene cuenta.
- **Ningun enlace de correo cambia nada al abrirse.** Los filtros antivirus de los
  buzones abren los enlaces para inspeccionarlos. Si el GET consumiera el token, el
  filtro gastaria el enlace antes que la persona. El GET muestra un boton; el POST
  hace el cambio.
- **Todo formulario que dispara un correo tiene tope.** Si no, sirven para bombardear
  la bandeja de un tercero con mensajes nuestros.
"""
import re
import secrets
from functools import lru_cache

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from db.usuarios import (
    cambiar_password,
    consumir_token,
    crear_token,
    crear_usuario,
    eliminar_usuario,
    get_usuario,
    get_usuario_por_email,
    hash_password,
    limite_superado,
    listar_usuarios,
    marcar_email_verificado,
    normalizar_email,
    registrar_intento,
    set_asesoria_habilitada,
    verificar_password,
)
from web.auth import (
    cerrar_sesion,
    iniciar_sesion,
    redirigir,
    requiere_admin,
    requiere_sesion,
    usuario_actual,
)
from web.correo import enviar_recuperacion, enviar_verificacion
from web.legal import documento
from web.templates_env import templates

router = APIRouter()

# NIST 800-63B: la longitud protege mas que las reglas de composicion, y obligar a
# mezclar simbolos solo empuja a patrones predecibles. El maximo existe porque scrypt
# procesa la clave completa: sin tope, una clave de un megabyte es un ataque de
# denegacion de servicio barato.
LARGO_MIN_PASSWORD = 10
LARGO_MAX_PASSWORD = 128

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TOPE_SUPERADO = "Demasiados intentos seguidos. Espera unos minutos y vuelve a probar."

# Mensajes de confirmacion por clave fija. La URL solo lleva la clave, nunca el
# texto: asi nadie puede fabricar un enlace que muestre un mensaje arbitrario.
AVISOS = {
    "password": "Tu contraseña quedó actualizada. Cerramos las demás sesiones abiertas.",
    "reenviado": "Te enviamos un enlace nuevo. El anterior ya no sirve.",
    "restablecida": "Contraseña restablecida. Ya estás dentro.",
}


def _ip(request: Request) -> str | None:
    """IP del cliente. Vercel escribe x-forwarded-for con la direccion real y descarta
    lo que traiga la peticion, asi que en produccion es fiable. En local se usa la del
    socket."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else None


@lru_cache(maxsize=1)
def _hash_ficticio() -> str:
    return hash_password(secrets.token_urlsafe(16))


def _validar_password(password: str, confirmacion: str, errores: list[str]) -> None:
    if len(password) < LARGO_MIN_PASSWORD:
        errores.append(f"La contraseña debe tener al menos {LARGO_MIN_PASSWORD} caracteres.")
    elif len(password) > LARGO_MAX_PASSWORD:
        errores.append(f"La contraseña no puede pasar de {LARGO_MAX_PASSWORD} caracteres.")
    elif password != confirmacion:
        errores.append("Las dos contraseñas no coinciden.")


def _pagina(request: Request, plantilla: str, contexto: dict | None = None, status: int = 200):
    return templates.TemplateResponse(request, plantilla, contexto or {}, status_code=status)


# --- acceso ------------------------------------------------------------------


@router.get("/entrar", response_class=HTMLResponse)
def entrar_form(request: Request):
    if usuario_actual(request):
        return redirigir("/")
    return _pagina(request, "entrar.html", {"errores": [], "email": ""})


@router.post("/entrar", response_class=HTMLResponse)
def entrar(request: Request, email: str = Form(""), password: str = Form("")):
    ip = _ip(request)

    def fallo(mensaje: str):
        return _pagina(request, "entrar.html", {"errores": [mensaje], "email": email}, 400)

    if limite_superado("acceso", email, ip):
        return fallo(TOPE_SUPERADO)

    usuario = get_usuario_por_email(email) if email else None
    # Si el correo no existe se verifica igual contra un hash de mentira. Sin esto,
    # la respuesta para un correo inexistente llegaria ~100 ms antes, y medir ese
    # tiempo bastaria para saber que cuentas existen.
    guardado = usuario["password_hash"] if usuario else _hash_ficticio()
    correcta = verificar_password(password[:LARGO_MAX_PASSWORD], guardado)

    if not usuario or not correcta:
        registrar_intento("acceso", email, ip, exitoso=False)
        return fallo("Correo o contraseña incorrectos.")

    registrar_intento("acceso", email, ip, exitoso=True)
    iniciar_sesion(request, usuario)
    # Si el correo no esta verificado, requiere_sesion lo mandara al aviso.
    return redirigir("/")


@router.post("/salir")
def salir(request: Request):
    cerrar_sesion(request)
    return redirigir("/entrar")


# --- alta --------------------------------------------------------------------


@router.get("/crear-cuenta", response_class=HTMLResponse)
def crear_cuenta_form(request: Request):
    if usuario_actual(request):
        return redirigir("/")
    return _pagina(request, "crear_cuenta.html", {"errores": [], "email": ""})


@router.post("/crear-cuenta", response_class=HTMLResponse)
def crear_cuenta(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    confirmacion: str = Form(""),
    acepta: str = Form(""),
):
    ip = _ip(request)
    errores: list[str] = []
    email = normalizar_email(email)

    if limite_superado("alta", None, ip):
        errores.append(TOPE_SUPERADO)
    if not _EMAIL.match(email) or len(email) > 254:
        errores.append("Escribe un correo válido.")
    _validar_password(password, confirmacion, errores)
    if not acepta:
        errores.append("Para crear la cuenta hay que aceptar los términos y la política de privacidad.")

    if errores:
        return _pagina(request, "crear_cuenta.html", {"errores": errores, "email": email}, 400)

    registrar_intento("alta", email, ip, exitoso=True)
    # Si el correo ya tiene cuenta no se crea nada ni se avisa en pantalla: la
    # respuesta es identica. El dueno real puede entrar o recuperar la clave.
    if not get_usuario_por_email(email):
        usuario_id = crear_usuario(email, password)
        enviar_verificacion(email, crear_token(usuario_id, "verificacion"))

    return _pagina(request, "revisa_correo.html", {"email": email})


# --- verificacion de correo --------------------------------------------------


@router.get("/verificar-aviso", response_class=HTMLResponse)
def verificar_aviso(request: Request):
    """Pantalla para quien inicio sesion pero aun no confirmo el correo.

    Usa usuario_actual y no requiere_sesion: esta ultima redirige justamente aca, y
    se formaria un bucle.
    """
    usuario = usuario_actual(request)
    if not usuario:
        return redirigir("/entrar")
    if usuario["email_verificado_en"]:
        return redirigir("/")
    return _pagina(
        request,
        "verificar_aviso.html",
        {"email": usuario["email"], "aviso": AVISOS.get(request.query_params.get("aviso", ""))},
    )


@router.post("/verificar-aviso/reenviar")
def verificar_reenviar(request: Request):
    usuario = usuario_actual(request)
    if not usuario:
        return redirigir("/entrar")
    if usuario["email_verificado_en"]:
        return redirigir("/")
    if limite_superado("reenvio", usuario["email"], _ip(request)):
        return redirigir("/verificar-aviso")
    registrar_intento("reenvio", usuario["email"], _ip(request), exitoso=True)
    enviar_verificacion(usuario["email"], crear_token(usuario["id"], "verificacion"))
    return redirigir("/verificar-aviso?aviso=reenviado")


@router.get("/verificar/{token}", response_class=HTMLResponse)
def verificar_form(request: Request, token: str):
    return _pagina(request, "verificar.html", {"token": token})


@router.post("/verificar/{token}", response_class=HTMLResponse)
def verificar(request: Request, token: str):
    usuario_id = consumir_token(token, "verificacion")
    if not usuario_id:
        return _pagina(request, "verificar.html", {"token": token, "invalido": True}, 400)
    marcar_email_verificado(usuario_id)
    iniciar_sesion(request, get_usuario(usuario_id))
    return redirigir("/config/activo")


# --- recuperacion ------------------------------------------------------------


@router.get("/recuperar", response_class=HTMLResponse)
def recuperar_form(request: Request):
    return _pagina(request, "recuperar.html", {"enviado": False, "errores": []})


@router.post("/recuperar", response_class=HTMLResponse)
def recuperar(request: Request, email: str = Form("")):
    ip = _ip(request)
    if limite_superado("recuperacion", email, ip):
        return _pagina(request, "recuperar.html", {"enviado": False, "errores": [TOPE_SUPERADO]}, 429)

    registrar_intento("recuperacion", email, ip, exitoso=True)
    usuario = get_usuario_por_email(email) if email else None
    if usuario:
        enviar_recuperacion(usuario["email"], crear_token(usuario["id"], "recuperacion"))
    # Misma pantalla exista o no la cuenta.
    return _pagina(request, "recuperar.html", {"enviado": True, "errores": []})


@router.get("/recuperar/{token}", response_class=HTMLResponse)
def recuperar_nueva_form(request: Request, token: str):
    return _pagina(request, "recuperar_nueva.html", {"token": token, "errores": []})


@router.post("/recuperar/{token}", response_class=HTMLResponse)
def recuperar_nueva(
    request: Request, token: str, password: str = Form(""), confirmacion: str = Form("")
):
    errores: list[str] = []
    _validar_password(password, confirmacion, errores)
    # La contrasena se valida antes de consumir el token: si se quemara primero, un
    # error de tipeo obligaria a pedir otro correo.
    if errores:
        return _pagina(request, "recuperar_nueva.html", {"token": token, "errores": errores}, 400)

    usuario_id = consumir_token(token, "recuperacion")
    if not usuario_id:
        return _pagina(
            request,
            "recuperar_nueva.html",
            {"token": token, "errores": ["El enlace venció o ya se usó. Pide uno nuevo."], "invalido": True},
            400,
        )

    cambiar_password(usuario_id, password)
    # Quien abrio el enlace del correo demostro que el buzon es suyo.
    marcar_email_verificado(usuario_id)
    iniciar_sesion(request, get_usuario(usuario_id))
    return redirigir("/cuenta?aviso=restablecida")


# --- perfil ------------------------------------------------------------------


@router.get("/cuenta", response_class=HTMLResponse)
def cuenta(request: Request):
    usuario = requiere_sesion(request)
    return _pagina(
        request,
        "cuenta.html",
        {
            "usuario": usuario,
            "errores": [],
            "errores_eliminar": [],
            "aviso": AVISOS.get(request.query_params.get("aviso", "")),
        },
    )


@router.post("/cuenta/password", response_class=HTMLResponse)
def cuenta_password(
    request: Request,
    actual: str = Form(""),
    password: str = Form(""),
    confirmacion: str = Form(""),
):
    usuario = requiere_sesion(request)
    errores: list[str] = []
    if not verificar_password(actual[:LARGO_MAX_PASSWORD], usuario["password_hash"]):
        errores.append("La contraseña actual no es correcta.")
    _validar_password(password, confirmacion, errores)
    if errores:
        return _pagina(
            request,
            "cuenta.html",
            {"usuario": usuario, "errores": errores, "errores_eliminar": [], "aviso": None},
            400,
        )

    cambiar_password(usuario["id"], password)
    # cambiar_password invalido todas las sesiones, incluida esta. Se reabre la del
    # usuario que acaba de cambiarla, con la version nueva.
    iniciar_sesion(request, get_usuario(usuario["id"]))
    return redirigir("/cuenta?aviso=password")


@router.post("/cuenta/eliminar", response_class=HTMLResponse)
def cuenta_eliminar(request: Request, password: str = Form("")):
    usuario = requiere_sesion(request)
    if not verificar_password(password[:LARGO_MAX_PASSWORD], usuario["password_hash"]):
        return _pagina(
            request,
            "cuenta.html",
            {
                "usuario": usuario,
                "errores": [],
                "errores_eliminar": ["La contraseña no es correcta. No se borró nada."],
                "aviso": None,
            },
            400,
        )
    # ON DELETE CASCADE arrastra el activo y todo su historico.
    eliminar_usuario(usuario["id"])
    cerrar_sesion(request)
    return _pagina(request, "cuenta_eliminada.html")


# --- legal -------------------------------------------------------------------


@router.get("/privacidad", response_class=HTMLResponse)
@router.get("/terminos", response_class=HTMLResponse)
def legal(request: Request):
    # Publicas: hay que poder leerlas antes de crear la cuenta. Se resuelve la sesion
    # si la hay solo para que el encabezado muestre el menu de cuenta.
    usuario_actual(request)
    titulo, cuerpo = documento(request.url.path.strip("/"))
    return _pagina(request, "legal.html", {"titulo_doc": titulo, "cuerpo": cuerpo})


# --- administracion ----------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    usuario = requiere_admin(request)
    return _pagina(request, "admin.html", {"usuario": usuario, "cuentas": listar_usuarios()})


@router.post("/admin/cuentas/{usuario_id}/asesoria")
def admin_asesoria(request: Request, usuario_id: int, habilitar: str = Form("")):
    requiere_admin(request)
    set_asesoria_habilitada(usuario_id, habilitar == "1")
    return redirigir("/admin")
