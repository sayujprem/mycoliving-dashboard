"""Inicializa el esquema de la base de datos a partir de db/schema.sql."""
from pathlib import Path

from config import DB_PATH
from db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Orden de borrado inverso a la creacion (respeta las llaves foraneas).
TABLAS = [
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
    """Crea las tablas y triggers si no existen."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def drop_all() -> None:
    """Borra todas las tablas. Solo para tests y para reconstruir en local."""
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for tabla in reversed(TABLAS):
            conn.execute(f"DROP TABLE IF EXISTS {tabla}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Base de datos inicializada en: {DB_PATH}")
