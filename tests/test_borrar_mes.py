"""Quitar un mes mal cargado desde el histórico.

Editar ya existía (re-registrar el mismo mes lo reemplaza). Lo que faltaba era borrarlo,
que no es solo un DELETE: arrastra las unidades, la asesoría del mes y obliga a rehacer
el fondo de reserva.
"""
import pytest
from fastapi.testclient import TestClient

from db.connection import get_connection
from db.init_db import drop_all, init_db
from db.repositorio import (
    get_activo,
    get_asesoria,
    get_reporte,
    get_reportes,
    get_reserva_movimientos,
)
from dominio.asesoria import generar_y_guardar
from main import app


class _Bloque:
    type = "tool_use"
    name = "entregar_asesoria"

    def __init__(self, entrada):
        self.input = entrada


class _ClienteOK:
    def __init__(self, entrada):
        self._r = type("R", (), {"content": [_Bloque(entrada)]})()
        self.messages = self

    def create(self, **kwargs):
        return self._r


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = TestClient(app)
    c.post("/config/activo", data={"nombre": "Coliving Granada", "tipo": "coliving",
           "unidades_totales": "5", "comision_administrador_pct": "10", "moneda": "COP",
           "ubicacion": "Armenia"}, follow_redirects=False)
    c.post("/config/politica", data={"porcentaje_libre": "40", "porcentaje_reinversion": "40",
           "porcentaje_reserva": "20"}, follow_redirects=False)
    c.post("/config/umbrales", data={
        "ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "80",
        "meses_consecutivos_baja_ocupacion_para_rojo": "2",
        "arriendo_promedio_unidad": "900000", "ventana_aviso_recordatorio_dias": "30",
    }, follow_redirects=False)
    return c


def _mes(client, mes, arrendadas=4):
    """Sin contrato maestro: el canon va dentro de gastos_fijos."""
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "2500000",
            "gastos_variables": "150000", "comision_admin": "360000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    return client.post("/registro", data=data, follow_redirects=False)


def _unidades_en_bd(anio, mes):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM reporte_unidad u "
            "JOIN reporte_mensual r ON r.id = u.reporte_mensual_id "
            "WHERE r.anio = ? AND r.mes = ?",
            (anio, mes),
        ).fetchone()["n"]
    finally:
        conn.close()


def test_quitar_mes_borra_reporte_y_unidades(client):
    _mes(client, 7)
    assert _unidades_en_bd(2026, 7) == 5

    r = client.post("/historico/2026/7/eliminar", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/historico"
    assert get_reporte(get_activo()["id"], 2026, 7) == (None, [])
    assert _unidades_en_bd(2026, 7) == 0


def test_quitar_mes_borra_su_asesoria(client):
    _mes(client, 7)
    activo_id = get_activo()["id"]
    entrada = {
        "causa_brecha": "Ocupación de 4 de 5 unidades.",
        "recomendacion_reinversion": "Sostener la reserva.",
        "nota_fiscal": "Estimación basada únicamente en el ingreso de este activo.",
    }
    generar_y_guardar(activo_id, 2026, 7, api_key="x", cliente=_ClienteOK(entrada))
    assert get_asesoria(activo_id, 2026, 7) is not None

    client.post("/historico/2026/7/eliminar", follow_redirects=False)
    assert get_asesoria(activo_id, 2026, 7) is None


def test_quitar_mes_recalcula_la_reserva(client):
    """El saldo es acumulativo: si no se recalcula, los meses que quedan mienten."""
    _mes(client, 7)
    _mes(client, 8)
    activo_id = get_activo()["id"]
    assert len(get_reserva_movimientos(activo_id)) == 2

    client.post("/historico/2026/7/eliminar", follow_redirects=False)
    movimientos = get_reserva_movimientos(activo_id)
    assert len(movimientos) == 1
    # Queda solo agosto: resultado = 3.600.000 - 360.000 - 2.650.000 = 590.000; 20% a reserva.
    assert movimientos[0]["mes"] == 8
    assert movimientos[0]["saldo_resultante"] == pytest.approx(0.20 * 590_000)


def test_quitar_un_mes_no_toca_los_demas(client):
    _mes(client, 7)
    _mes(client, 8)
    client.post("/historico/2026/7/eliminar", follow_redirects=False)

    reporte, unidades = get_reporte(get_activo()["id"], 2026, 8)
    assert reporte is not None
    assert len(unidades) == 5
    assert len(get_reportes(get_activo()["id"])) == 1


def test_quitar_un_mes_inexistente_no_revienta(client):
    _mes(client, 7)
    r = client.post("/historico/2020/1/eliminar", follow_redirects=False)
    assert r.status_code == 303
    assert len(get_reportes(get_activo()["id"])) == 1


def test_historico_ofrece_quitar_cada_mes(client):
    _mes(client, 7)
    html = client.get("/historico").text
    assert 'action="/historico/2026/7/eliminar"' in html
    assert ">Quitar<" in html
    # El borrado es irreversible y arrastra la asesoría: pide confirmación.
    assert "confirm(" in html
