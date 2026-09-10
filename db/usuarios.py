"""Cuentas: alta, verificacion de correo, contrasenas y control de intentos.

Sobre el hash de contrasenas: se usa `hashlib.scrypt`, de la biblioteca estandar.
No hay dependencia de passlib ni de bcrypt a proposito. scrypt es una funcion de
derivacion de clave deliberadamente costosa en memoria (los parametros de abajo piden
unos 16 MB por intento), que es lo que la hace cara de atacar con GPU. Cada contrasena
lleva su propia sal, asi que dos usuarios con la misma clave tienen hashes distintos.

Las funciones de este modulo abren la base en modo privilegiado: operan sobre tablas
que no llevan RLS (`usuario`, `token_email`, `intento_acceso`) y se ejecutan antes de
que exista una identidad contra la cual filtrar. Es el unico lugar de la aplicacion,
junto con los scripts, donde eso es correcto.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from db.connection import db_cursor

# Coste del hash. n es el factor de trabajo: 2**14 pide ~16 MB y tarda del orden de
# 100 ms, que es imperceptible al iniciar sesion e inviable para probar millones de
# claves. Subirlo encarece tambien nuestra propia funcion, que tiene memoria acotada.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_LARGO_CLAVE = 32
_LARGO_SAL = 16

VIGENCIA_VERIFICACION = timedelta(hours=24)
VIGENCIA_RECUPERACION = timedelta(hours=1)


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def hash_password(password: str) -> str:
    """Devuelve `scrypt$n$r$p$sal$hash`, todo lo necesario para verificar despues."""
    sal = secrets.token_bytes(_LARGO_SAL)
    clave = hashlib.scrypt(
        password.encode("utf-8"),
        salt=sal,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_LARGO_CLAVE,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(sal)}${_b64(clave)}"


def verificar_password(password: str, guardado: str) -> bool:
    """Compara en tiempo constante. Un hash con formato roto es un fallo, no una excepcion."""
    try:
        etiqueta, n, r, p, sal_b64, esperado_b64 = guardado.split("$")
        if etiqueta != "scrypt":
            return False
        calculado = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(sal_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(esperado_b64)),
        )
    except (ValueError, TypeError):
        return False
    # compare_digest evita filtrar por cuanto tarda la comparacion.
    return hmac.compare_digest(calculado, base64.b64decode(esperado_b64))


def normalizar_email(email: str) -> str:
    return email.strip().lower()


# --- cuentas -----------------------------------------------------------------


def crear_usuario(email: str, password: str, es_admin: bool = False) -> int:
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "INSERT INTO usuario (email, password_hash, es_admin) VALUES (%s, %s, %s) "
            "RETURNING id",
            (normalizar_email(email), hash_password(password), es_admin),
        )
        return cur.fetchone()["id"]


def get_usuario_por_email(email: str) -> dict | None:
    with db_cursor(privilegiado=True) as cur:
        cur.execute("SELECT * FROM usuario WHERE email = %s", (normalizar_email(email),))
        return cur.fetchone()


def get_usuario(usuario_id: int) -> dict | None:
    with db_cursor(privilegiado=True) as cur:
        cur.execute("SELECT * FROM usuario WHERE id = %s", (usuario_id,))
        return cur.fetchone()


def marcar_email_verificado(usuario_id: int) -> None:
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "UPDATE usuario SET email_verificado_en = now() WHERE id = %s AND email_verificado_en IS NULL",
            (usuario_id,),
        )


def cambiar_password(usuario_id: int, nueva: str) -> None:
    """Cambia la clave e invalida toda sesion abierta de esa cuenta.

    El incremento de token_sesion es lo que cierra las sesiones: la cookie lleva el
    valor con el que se emitio y deja de coincidir.
    """
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "UPDATE usuario SET password_hash = %s, token_sesion = token_sesion + 1 WHERE id = %s",
            (hash_password(nueva), usuario_id),
        )


def eliminar_usuario(usuario_id: int) -> None:
    """Borra la cuenta y, en cascada, el activo y todo su historico."""
    with db_cursor(privilegiado=True) as cur:
        cur.execute("DELETE FROM usuario WHERE id = %s", (usuario_id,))


# --- tokens de correo --------------------------------------------------------


def crear_token(usuario_id: int, tipo: str) -> str:
    """Emite un token de un solo uso y devuelve el valor en claro.

    En la base solo queda su SHA-256. Quien lea la tabla no puede reconstruirlo, asi
    que una filtracion de la base no permite verificar cuentas ni cambiar contrasenas.
    """
    vigencia = VIGENCIA_VERIFICACION if tipo == "verificacion" else VIGENCIA_RECUPERACION
    token = secrets.token_urlsafe(32)
    with db_cursor(privilegiado=True) as cur:
        # Un token nuevo anula los anteriores del mismo tipo: pedir otro enlace
        # invalida el que ya se habia enviado.
        cur.execute(
            "DELETE FROM token_email WHERE usuario_id = %s AND tipo = %s",
            (usuario_id, tipo),
        )
        cur.execute(
            "INSERT INTO token_email (usuario_id, tipo, hash_token, expira_en) "
            "VALUES (%s, %s, %s, %s)",
            (
                usuario_id,
                tipo,
                hashlib.sha256(token.encode()).hexdigest(),
                datetime.now(timezone.utc) + vigencia,
            ),
        )
    return token


def consumir_token(token: str, tipo: str) -> int | None:
    """Valida y quema el token. Devuelve el usuario, o None si no sirve."""
    hash_token = hashlib.sha256(token.encode()).hexdigest()
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "UPDATE token_email SET usado_en = now() "
            "WHERE hash_token = %s AND tipo = %s AND usado_en IS NULL AND expira_en > now() "
            "RETURNING usuario_id",
            (hash_token, tipo),
        )
        fila = cur.fetchone()
        return fila["usuario_id"] if fila else None


# --- control de intentos -----------------------------------------------------

# Ventanas deslizantes. Frenan la fuerza bruta y el abuso del envio de correos sin
# necesidad de Redis ni de un servicio aparte: a esta escala, contar filas sobra.
#
# Cada regla es (tipo, por que se cuenta, tope, ventana, solo fallidos). Los fallos
# de inicio de sesion se cuentan por correo (protege una cuenta concreta) y por IP
# (frena a quien prueba muchas cuentas). Las altas y los envios de correo se cuentan
# todos, fallen o no, porque lo que se limita es el volumen.
_LIMITES = {
    "acceso": (("email", 5, "15 minutes", True), ("ip", 20, "15 minutes", True)),
    "alta": (("ip", 3, "1 hour", False),),
    "recuperacion": (("ip", 5, "1 hour", False), ("email", 3, "1 hour", False)),
    "reenvio": (("email", 3, "1 hour", False),),
}


def registrar_intento(tipo: str, email: str | None, ip: str | None, exitoso: bool = False) -> None:
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "INSERT INTO intento_acceso (tipo, email, ip, exitoso) VALUES (%s, %s, %s, %s)",
            (tipo, normalizar_email(email) if email else None, ip, exitoso),
        )


def limite_superado(tipo: str, email: str | None, ip: str | None) -> bool:
    """True si este correo o esta IP ya agotaron el cupo del flujo `tipo`."""
    valores = {"email": normalizar_email(email) if email else None, "ip": ip}
    with db_cursor(privilegiado=True) as cur:
        for columna, tope, ventana, solo_fallidos in _LIMITES[tipo]:
            if valores[columna] is None:
                continue
            filtro_fallo = "AND NOT exitoso" if solo_fallidos else ""
            # columna, ventana y filtro salen de _LIMITES, nunca de la peticion.
            cur.execute(
                f"SELECT count(*) AS n FROM intento_acceso "
                f"WHERE tipo = %s AND {columna} = %s {filtro_fallo} "
                f"AND ts > now() - INTERVAL '{ventana}'",
                (tipo, valores[columna]),
            )
            if cur.fetchone()["n"] >= tope:
                return True
    return False


# --- administracion ----------------------------------------------------------


def listar_usuarios() -> list[dict]:
    """Para /admin. La ruta que llama aca ya comprobo es_admin."""
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.creado_en, u.email_verificado_en,
                   u.asesoria_habilitada, u.es_admin,
                   a.nombre AS activo_nombre,
                   (SELECT count(*) FROM uso_asesoria x WHERE x.usuario_id = u.id) AS asesorias_usadas
            FROM usuario u
            LEFT JOIN activo a ON a.usuario_id = u.id
            ORDER BY u.creado_en DESC
            """
        )
        return cur.fetchall()


def set_asesoria_habilitada(usuario_id: int, habilitada: bool) -> None:
    with db_cursor(privilegiado=True) as cur:
        cur.execute(
            "UPDATE usuario SET asesoria_habilitada = %s WHERE id = %s",
            (habilitada, usuario_id),
        )


def registrar_uso_asesoria(usuario_id: int, anio: int, mes: int) -> None:
    """Deja rastro de cada llamada al modelo. Es la auditoria de gasto propia,
    independiente de lo que reporte la consola de Anthropic."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO uso_asesoria (usuario_id, anio, mes) VALUES (%s, %s, %s)",
            (usuario_id, anio, mes),
        )
