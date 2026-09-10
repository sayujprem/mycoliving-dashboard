"""Tarea 5: registro mensual del informe e histórico."""
import pytest

from db.init_db import drop_all, init_db
from db.repositorio import get_reportes
from tests.apoyo import activo_actual, nuevo_cliente


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = nuevo_cliente()
    c.post(
        "/config/activo",
        data={
            "nombre": "Coliving Granada",
            "tipo": "coliving",
            "unidades_totales": "5",
            "comision_administrador_pct": "10",
            "moneda": "COP",
        },
        follow_redirects=False,
    )
    return c


def _mes_valido(**over):
    data = {
        "mes": "7",
        "anio": "2026",
        "gastos_fijos": "600000",
        "gastos_variables": "300000",
        "comision_admin": "715000",
        "novedades": "sin incidencias",
        "unidad_1_arrendada": "1",
        "unidad_1_ingreso": "900000",
        "unidad_2_arrendada": "1",
        "unidad_2_ingreso": "850000",
        "unidad_3_arrendada": "1",
        "unidad_3_ingreso": "900000",
        "unidad_4_arrendada": "1",
        "unidad_4_ingreso": "900000",
    }
    data.update(over)
    return data


def test_sin_activo_redirige(client):
    # "Sin activo" ya no es una base vacía sino una cuenta que aún no lo configuró.
    client = nuevo_cliente("sin-activo@ejemplo.com")
    r = client.get("/registro", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/config/activo"


def test_form_muestra_una_fila_por_unidad(client):
    r = client.get("/registro")
    assert r.status_code == 200
    assert r.text.count('name="unidad_') >= 5 * 2  # checkbox + ingreso por unidad
    assert "Unidad 5" in r.text


def test_registro_valido_persiste_y_deriva_ocupacion(client):
    r = client.post("/registro", data=_mes_valido(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/historico"
    reportes = get_reportes(activo_actual()["id"])
    assert len(reportes) == 1
    assert reportes[0]["ocupacion"] == 4
    assert reportes[0]["ingreso_subarriendo"] == 3550000.0


def test_re_registrar_mismo_mes_reemplaza(client):
    client.post("/registro", data=_mes_valido(), follow_redirects=False)
    client.post(
        "/registro",
        data=_mes_valido(unidad_4_arrendada="", unidad_4_ingreso=""),
        follow_redirects=False,
    )
    reportes = get_reportes(activo_actual()["id"])
    assert len(reportes) == 1
    assert reportes[0]["ocupacion"] == 3


def test_rechaza_gastos_vacios(client):
    r = client.post("/registro", data=_mes_valido(gastos_fijos=""))
    assert r.status_code == 400
    assert get_reportes(activo_actual()["id"]) == []


def test_rechaza_unidad_arrendada_sin_ingreso(client):
    r = client.post("/registro", data=_mes_valido(unidad_2_ingreso=""))
    assert r.status_code == 400
    assert "sin ingreso" in r.text
    assert get_reportes(activo_actual()["id"]) == []


def test_historico_vacio_muestra_aviso(client):
    r = client.get("/historico")
    assert r.status_code == 200
    assert "Todavía no hay meses registrados" in r.text
