"""Inicializa el esquema de la base de datos a partir de db/schema.sql."""
from pathlib import Path

from db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Orden de creacion. El borrado va al reves, con CASCADE, asi que el orden solo
# importa como documentacion de las dependencias.
TABLAS = [
    "usuario",
    "token_email",
    "intento_acceso",
    "uso_asesoria",
    "activo",
    "contrato_maestro",
    "politica_distribucion",
    "configuracion_dominio",
    "capex",
    "recordatorios",
    "reporte_mensual",
    "reporte_unidad",
    "reserva_movimiento",
    "asesoria_generada",
]


def init_db() -> None:
    """Crea tablas, indices, triggers y politicas de aislamiento si no existen.

    Se ejecuta con el rol de conexion (no con el rol acotado de la aplicacion): crear
    roles y politicas requiere privilegios que mycoliving_app no tiene, ni debe tener.
    """
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Sin parametros, psycopg manda el guion completo al servidor y este
                # entiende el dollar-quoting de los bloques DO y las funciones.
                cur.execute(schema)
    finally:
        conn.close()


def drop_all() -> None:
    """Borra todas las tablas. Solo para tests y para reconstruir en local."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for tabla in reversed(TABLAS):
                    cur.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")
                cur.execute("DROP FUNCTION IF EXISTS fn_valida_ocupacion() CASCADE")
                cur.execute("DROP FUNCTION IF EXISTS app_usuario_id() CASCADE")
                cur.execute("DROP FUNCTION IF EXISTS limpiar_intentos_viejos() CASCADE")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Esquema inicializado.")
