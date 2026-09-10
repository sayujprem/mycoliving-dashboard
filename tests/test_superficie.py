"""La base no queda expuesta por la Data API de Supabase.

Supabase publica el esquema public por HTTP (PostgREST) para los roles anon y
authenticated, cuya clave es publica, y les concede por defecto todos los permisos sobre
las tablas nuevas. Esta prueba reproduce esa configuracion en la base de pruebas y
comprueba que, tras aplicar el esquema, esos roles no pueden leer ni ejecutar nada.
"""
import pytest

from db.connection import get_connection
from db.init_db import TABLAS, drop_all, init_db

ROLES_PUBLICOS = ("anon", "authenticated")


@pytest.fixture(scope="module")
def conn():
    c = get_connection()
    c.autocommit = True
    # Lo mismo que trae de fabrica un proyecto de Supabase.
    for rol in ROLES_PUBLICOS:
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,)).fetchone():
            c.execute(f"CREATE ROLE {rol} NOLOGIN")
    c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
    c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated")
    c.execute("GRANT USAGE ON SCHEMA public TO anon, authenticated")
    drop_all()
    init_db()
    yield c
    c.close()


@pytest.mark.parametrize("rol", ROLES_PUBLICOS)
def test_los_roles_publicos_no_pueden_leer_ninguna_tabla(conn, rol):
    for tabla in TABLAS:
        puede = conn.execute(
            "SELECT has_table_privilege(%s, %s, 'SELECT') AS p", (rol, f"public.{tabla}")
        ).fetchone()["p"]
        assert not puede, f"{rol} puede leer {tabla}"


@pytest.mark.parametrize("rol", ROLES_PUBLICOS)
def test_los_roles_publicos_no_pueden_ejecutar_las_funciones(conn, rol):
    for funcion in ("app_usuario_id()", "limpiar_intentos_viejos()"):
        puede = conn.execute(
            "SELECT has_function_privilege(%s, %s, 'EXECUTE') AS p", (rol, f"public.{funcion}")
        ).fetchone()["p"]
        assert not puede, f"{rol} puede ejecutar {funcion}"


def test_ni_siquiera_el_rol_de_la_app_lee_las_tablas_de_cuentas(conn):
    """RLS sin politicas: solo el rol de conexion (modo privilegiado) las ve."""
    conn.execute("INSERT INTO usuario (email, password_hash) VALUES ('a@b.co', 'x')")
    with conn.transaction():
        conn.execute("SET LOCAL ROLE mycoliving_app")
        for tabla in ("usuario", "token_email", "intento_acceso"):
            n = conn.execute(f"SELECT count(*) AS n FROM {tabla}").fetchone()["n"]
            assert n == 0, f"mycoliving_app ve filas de {tabla}"


def test_todas_las_tablas_tienen_rls(conn):
    sin_rls = conn.execute(
        "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
    ).fetchall()
    assert [f["relname"] for f in sin_rls] == []
