"""Tarea 2: el modelo de datos en PostgreSQL.

Estas pruebas hablan con la base directamente y con el rol de conexion, sin pasar por
la aplicacion: lo que se prueba es que las reglas vivan en el esquema, de modo que
se cumplan aunque algun dia alguien escriba en la base por otro camino.
"""
import psycopg
import pytest

from db.connection import get_connection
from db.init_db import TABLAS, drop_all, init_db


@pytest.fixture
def conn():
    drop_all()
    init_db()
    c = get_connection()
    # Cada sentencia en su propia transaccion: en Postgres, un error aborta la
    # transaccion entera y las pruebas que esperan un rechazo contaminarian a las demas.
    c.autocommit = True
    yield c
    c.close()


def _crear_usuario(conn, email="ana@ejemplo.com"):
    return conn.execute(
        "INSERT INTO usuario (email, password_hash) VALUES (%s, 'x') RETURNING id", (email,)
    ).fetchone()["id"]


def _crear_activo(conn, unidades, usuario_id=None):
    usuario_id = usuario_id or _crear_usuario(conn)
    return conn.execute(
        "INSERT INTO activo (usuario_id, nombre, tipo, unidades_totales, comision_administrador_pct, moneda) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (usuario_id, "Coliving Prueba", "coliving", unidades, 10.0, "COP"),
    ).fetchone()["id"]


def _crear_reporte(conn, activo_id):
    return conn.execute(
        "INSERT INTO reporte_mensual (activo_id, mes, anio, fecha_registro) VALUES (%s, %s, %s, %s) RETURNING id",
        (activo_id, 8, 2026, "2026-08-31"),
    ).fetchone()["id"]


def _columnas(conn, tabla):
    filas = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (tabla,),
    ).fetchall()
    return {f["column_name"]: f["data_type"] for f in filas}


# --- estructura ---


def test_todas_las_tablas_existen(conn):
    filas = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    nombres = {f["tablename"] for f in filas}
    for tabla in TABLAS:
        assert tabla in nombres, f"falta la tabla {tabla}"


def test_tablas_de_negocio_llevan_activo_id(conn):
    de_negocio = ["contrato_maestro", "politica_distribucion", "configuracion_dominio", "capex",
                  "recordatorios", "reporte_mensual", "reserva_movimiento", "asesoria_generada"]
    for tabla in de_negocio:
        assert "activo_id" in _columnas(conn, tabla), f"{tabla} no tiene activo_id"


def test_el_dinero_se_guarda_en_numeric_y_nunca_en_punto_flotante(conn):
    """REAL en Postgres tiene 7 digitos significativos: un canon de 12.345.678 pesos
    se guardaria como 12.345.680."""
    montos = {
        "contrato_maestro": "canon_mensual",
        "capex": "monto",
        "reporte_mensual": "gastos_fijos",
        "reporte_unidad": "ingreso_inquilino",
        "reserva_movimiento": "saldo_resultante",
    }
    for tabla, columna in montos.items():
        assert _columnas(conn, tabla)[columna] == "numeric", f"{tabla}.{columna}"


def test_un_monto_grande_se_conserva_exacto(conn):
    activo_id = _crear_activo(conn, unidades=5)
    conn.execute(
        "INSERT INTO capex (activo_id, concepto, monto, fecha, horizonte_meses) "
        "VALUES (%s, 'x', 123456789.99, '2026-01-01', 12)",
        (activo_id,),
    )
    assert conn.execute("SELECT monto FROM capex").fetchone()["monto"] == 123456789.99


def test_las_tablas_de_negocio_tienen_rls_activo(conn):
    filas = conn.execute("SELECT relname FROM pg_class WHERE relrowsecurity").fetchall()
    con_rls = {f["relname"] for f in filas}
    for tabla in ("activo", "reporte_mensual", "reporte_unidad", "capex", "asesoria_generada"):
        assert tabla in con_rls, f"{tabla} no tiene RLS"


# --- cuentas ---


def test_una_cuenta_tiene_como_maximo_un_activo(conn):
    usuario_id = _crear_usuario(conn)
    _crear_activo(conn, unidades=5, usuario_id=usuario_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _crear_activo(conn, unidades=3, usuario_id=usuario_id)


def test_el_correo_se_guarda_en_minusculas(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        _crear_usuario(conn, "Ana@Ejemplo.com")


def test_borrar_la_cuenta_borra_todo_su_rastro(conn):
    usuario_id = _crear_usuario(conn)
    activo_id = _crear_activo(conn, unidades=2, usuario_id=usuario_id)
    reporte_id = _crear_reporte(conn, activo_id)
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada) VALUES (%s, 'A', true)",
        (reporte_id,),
    )
    conn.execute(
        "INSERT INTO capex (activo_id, concepto, monto, fecha, horizonte_meses) VALUES (%s, 'x', 1, '2026-01-01', 1)",
        (activo_id,),
    )

    conn.execute("DELETE FROM usuario WHERE id = %s", (usuario_id,))

    for tabla in ("activo", "reporte_mensual", "reporte_unidad", "capex"):
        n = conn.execute(f"SELECT count(*) AS n FROM {tabla}").fetchone()["n"]
        assert n == 0, f"quedaron filas en {tabla}"


def test_la_limpieza_borra_los_intentos_de_acceso_viejos(conn):
    """La politica de privacidad promete que IP y correo de los intentos no duran mas
    de 7 dias. El flujo de mantenimiento llama a esta funcion cada cuatro."""
    conn.execute("INSERT INTO intento_acceso (email, ip, ts) VALUES ('viejo@x.co', '1.1.1.1', now() - INTERVAL '2 days')")
    conn.execute("INSERT INTO intento_acceso (email, ip) VALUES ('nuevo@x.co', '2.2.2.2')")
    conn.execute("SELECT limpiar_intentos_viejos()")
    quedan = [f["email"] for f in conn.execute("SELECT email FROM intento_acceso").fetchall()]
    assert quedan == ["nuevo@x.co"]


# --- reglas de negocio ---


def test_ocupacion_no_puede_superar_las_unidades_del_activo(conn):
    activo_id = _crear_activo(conn, unidades=2)
    reporte_id = _crear_reporte(conn, activo_id)
    for label in ("A", "B"):
        conn.execute(
            "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
            "VALUES (%s, %s, true, 800000)",
            (reporte_id, label),
        )
    with pytest.raises(psycopg.Error, match="supera las unidades"):
        conn.execute(
            "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
            "VALUES (%s, 'C', true, 800000)",
            (reporte_id,),
        )


def test_la_regla_de_ocupacion_tambien_frena_un_update(conn):
    activo_id = _crear_activo(conn, unidades=1)
    reporte_id = _crear_reporte(conn, activo_id)
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada) VALUES (%s, 'A', true)",
        (reporte_id,),
    )
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada) VALUES (%s, 'B', false)",
        (reporte_id,),
    )
    with pytest.raises(psycopg.Error, match="supera las unidades"):
        conn.execute("UPDATE reporte_unidad SET arrendada = true WHERE unidad_label = 'B'")


def test_unidad_no_arrendada_no_cuenta_para_el_limite(conn):
    activo_id = _crear_activo(conn, unidades=2)
    reporte_id = _crear_reporte(conn, activo_id)
    for label in ("A", "B"):
        conn.execute(
            "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
            "VALUES (%s, %s, true, 800000)",
            (reporte_id, label),
        )
    # Una tercera fila desocupada no debe fallar.
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
        "VALUES (%s, 'C', false, 0)",
        (reporte_id,),
    )


def test_politica_rechaza_porcentajes_que_no_suman_100(conn):
    activo_id = _crear_activo(conn, unidades=5)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO politica_distribucion "
            "(activo_id, porcentaje_libre, porcentaje_reinversion, porcentaje_reserva, fecha_definicion) "
            "VALUES (%s, 50, 30, 10, %s)",
            (activo_id, "2026-08-31"),
        )


def test_politica_acepta_porcentajes_que_suman_100(conn):
    activo_id = _crear_activo(conn, unidades=5)
    conn.execute(
        "INSERT INTO politica_distribucion "
        "(activo_id, porcentaje_libre, porcentaje_reinversion, porcentaje_reserva, fecha_definicion) "
        "VALUES (%s, 60, 30, 10, %s)",
        (activo_id, "2026-08-31"),
    )


def test_reporte_mensual_unico_por_activo_y_periodo(conn):
    activo_id = _crear_activo(conn, unidades=5)
    _crear_reporte(conn, activo_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO reporte_mensual (activo_id, mes, anio, fecha_registro) VALUES (%s, 8, 2026, %s)",
            (activo_id, "2026-09-01"),
        )
