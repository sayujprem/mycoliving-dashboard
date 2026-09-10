"""Configuracion del proyecto, leida de variables de entorno.

No hay valores de negocio aca. Los datos del activo (numero de unidades, comision,
umbrales) viven en la base de datos, no en el codigo.

Las variables sin las que la aplicacion no puede correr de forma segura no tienen
valor por defecto: si faltan, el import revienta. Es deliberado. Un default de
conveniencia para DATABASE_URL o SESSION_SECRET es exactamente como se despliega
una aplicacion insegura sin darse cuenta.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Carga variables desde .env si existe (no sobrescribe las ya presentes en el entorno).
load_dotenv(BASE_DIR / ".env")


def _requerido(nombre: str, pista: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(
            f"Falta la variable de entorno {nombre}. {pista}\n"
            f"En local se define en .env; en produccion, en las variables del proyecto."
        )
    return valor


# --- Base de datos -----------------------------------------------------------

# Cadena de conexion a PostgreSQL. Debe apuntar al *transaction pooler* (puerto 6543),
# no a la conexion directa: la aplicacion corre como funcion sin estado y abre muchas
# conexiones cortas.
DATABASE_URL = _requerido(
    "DATABASE_URL",
    "Es la cadena del transaction pooler de Supabase (puerto 6543).",
)

# Rol sin BYPASSRLS al que se cambia cada transaccion para que las politicas de
# Row Level Security se apliquen de verdad. Ver db/schema.sql.
DB_ROL_APP = os.environ.get("DB_ROL_APP", "mycoliving_app")


# --- Sesiones ----------------------------------------------------------------

# Clave de firma de la cookie de sesion. 32 bytes aleatorios en base64.
# Generar con: python -c "import secrets; print(secrets.token_urlsafe(32))"
# Cambiarla cierra la sesion de todos los usuarios; no es destructivo.
SESSION_SECRET = _requerido(
    "SESSION_SECRET",
    "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
)

SESSION_COOKIE = "mcl_sesion"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 dias

# En local no hay HTTPS, asi que la cookie no puede exigir Secure o el navegador
# la descarta y no se puede iniciar sesion. En produccion siempre es True.
ENTORNO = os.environ.get("MYCOLIVING_ENTORNO", "desarrollo")
ES_PRODUCCION = ENTORNO == "produccion"


# --- URL publica -------------------------------------------------------------

# Base de los enlaces que se envian por correo (verificacion, recuperacion).
APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000").rstrip("/")


# --- Anthropic ---------------------------------------------------------------

# Clave del API de Anthropic. Solo se usa para el informe de asesoria, que esta
# apagado por defecto en cada cuenta y se habilita desde /admin.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Requerido solo si la API key esta ligada a una identidad/organizacion con workspaces.
ANTHROPIC_WORKSPACE_ID = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")

# Modelo para el informe de asesoria. Sonnet 5 cuesta 2 USD por millon de tokens de
# entrada y 10 por millon de salida: alrededor de 0.05 USD por informe.
MODELO_ASESORIA = os.environ.get("MYCOLIVING_MODELO", "claude-sonnet-5")

# Tope de espera de la llamada al modelo, en segundos. La funcion en Vercel se corta a
# los 120 (maxDuration en vercel.json), asi que este numero queda por debajo: si el
# modelo tarda, el error lo da el SDK con un mensaje util en vez de morir la funcion.
ANTHROPIC_TIMEOUT = int(os.environ.get("MYCOLIVING_TIMEOUT", "100"))


# --- Correo (SMTP de Gmail) --------------------------------------------------

# Cuenta que envia los correos de verificacion y recuperacion. Es la misma que figura
# como contacto de privacidad, asi que las respuestas de los usuarios llegan ahi.
SMTP_USUARIO = os.environ.get("SMTP_USUARIO", "privacidad.mycoliving@gmail.com").strip()

# Contrasena de aplicacion de Google (16 letras), no la contrasena de la cuenta. Se
# crea en myaccount.google.com/apppasswords y exige la verificacion en dos pasos. Google
# la muestra en grupos de cuatro separados por espacios; los espacios se descartan.
SMTP_CLAVE = os.environ.get("SMTP_CLAVE", "").replace(" ", "")

# Correo de la cuenta que se marca como administradora al migrar los datos iniciales.
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
