"""Tarea 2: el modelo de datos en SQLite."""
import sqlite3

import pytest

from db.connection import get_connection
from db.init_db import TABLAS, drop_all, init_db


@pytest.fixture
def conn():
    drop_all()
    init_db()
    c = get_connection()
    yield c
    c.close()


def _crear_activo(conn, unidades):
    cur = conn.execute(
        "INSERT INTO activo (nombre, tipo, unidades_totales, comision_administrador_pct, moneda) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Coliving Prueba", "coliving", unidades, 10.0, "COP"),
    )
    conn.commit()
    return cur.lastrowid


def _crear_reporte(conn, activo_id):
    cur = conn.execute(
        "INSERT INTO reporte_mensual (activo_id, mes, anio, fecha_registro) VALUES (?, ?, ?, ?)",
        (activo_id, 8, 2026, "2026-08-31"),
    )
    conn.commit()
    return cur.lastrowid


def test_todas_las_tablas_existen(conn):
    filas = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    nombres = {f["name"] for f in filas}
    for tabla in TABLAS:
        assert tabla in nombres, f"falta la tabla {tabla}"


def test_tablas_de_datos_llevan_activo_id(conn):
    # 'activo' es la raiz; 'reporte_unidad' cuelga de reporte_mensual (activo_id via el padre).
    con_activo_id = [t for t in TABLAS if t not in ("activo", "reporte_unidad")]
    for tabla in con_activo_id:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({tabla})")}
        assert "activo_id" in cols, f"{tabla} no tiene activo_id"


def test_ocupacion_no_puede_superar_las_unidades_del_activo(conn):
    activo_id = _crear_activo(conn, unidades=2)
    reporte_id = _crear_reporte(conn, activo_id)
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
        "VALUES (?, 'A', 1, 800000)",
        (reporte_id,),
    )
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
        "VALUES (?, 'B', 1, 800000)",
        (reporte_id,),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
            "VALUES (?, 'C', 1, 800000)",
            (reporte_id,),
        )


def test_unidad_no_arrendada_no_cuenta_para_el_limite(conn):
    activo_id = _crear_activo(conn, unidades=2)
    reporte_id = _crear_reporte(conn, activo_id)
    for label in ("A", "B"):
        conn.execute(
            "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
            "VALUES (?, ?, 1, 800000)",
            (reporte_id, label),
        )
    # Una tercera fila desocupada no debe fallar.
    conn.execute(
        "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
        "VALUES (?, 'C', 0, 0)",
        (reporte_id,),
    )
    conn.commit()


def test_politica_rechaza_porcentajes_que_no_suman_100(conn):
    activo_id = _crear_activo(conn, unidades=5)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO politica_distribucion "
            "(activo_id, porcentaje_libre, porcentaje_reinversion, porcentaje_reserva, fecha_definicion) "
            "VALUES (?, 50, 30, 10, ?)",
            (activo_id, "2026-08-31"),
        )


def test_politica_acepta_porcentajes_que_suman_100(conn):
    activo_id = _crear_activo(conn, unidades=5)
    conn.execute(
        "INSERT INTO politica_distribucion "
        "(activo_id, porcentaje_libre, porcentaje_reinversion, porcentaje_reserva, fecha_definicion) "
        "VALUES (?, 60, 30, 10, ?)",
        (activo_id, "2026-08-31"),
    )
    conn.commit()


def test_reporte_mensual_unico_por_activo_y_periodo(conn):
    activo_id = _crear_activo(conn, unidades=5)
    _crear_reporte(conn, activo_id)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reporte_mensual (activo_id, mes, anio, fecha_registro) VALUES (?, 8, 2026, ?)",
            (activo_id, "2026-09-01"),
        )
