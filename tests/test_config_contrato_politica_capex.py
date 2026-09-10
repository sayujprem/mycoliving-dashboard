"""Tarea 4: contrato maestro, política de distribución y capex."""
import pytest

from db.init_db import drop_all, init_db
from db.repositorio import (
    get_capex,
    get_contrato_maestro,
    get_politica,
)
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


def _guardar_contrato(client, **over):
    data = {
        "canon_mensual": "3000000",
        "fecha_inicio": "2026-01-01",
        "fecha_vencimiento": "2031-01-01",
        "vigencia_meses": "60",
        "regla_reajuste": "IPC anual",
        "ventana_preaviso_dias": "90",
    }
    data.update(over)
    return client.post("/config/contrato", data=data, follow_redirects=False)


def test_contrato_maestro_persiste(client):
    r = _guardar_contrato(client)
    assert r.status_code == 303
    contrato = get_contrato_maestro(activo_actual()["id"])
    assert contrato["canon_mensual"] == 3000000.0
    assert contrato["vigencia_meses"] == 60


def test_contrato_rechaza_sin_fecha_inicio(client):
    r = _guardar_contrato(client, fecha_inicio="")
    assert r.status_code == 400
    assert get_contrato_maestro(activo_actual()["id"]) is None


def test_politica_suma_100_persiste(client):
    r = client.post(
        "/config/politica",
        data={
            "porcentaje_libre": "40",
            "porcentaje_reinversion": "40",
            "porcentaje_reserva": "20",
            "calcular_impuesto": "1",
            "tarifa_marginal_actual": "19",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    pol = get_politica(activo_actual()["id"])
    assert pol["porcentaje_libre"] == 40.0
    assert pol["calcular_impuesto"] == 1
    assert pol["tarifa_marginal_actual"] == 19.0


def test_politica_rechaza_suma_distinta_de_100(client):
    r = client.post(
        "/config/politica",
        data={
            "porcentaje_libre": "40",
            "porcentaje_reinversion": "40",
            "porcentaje_reserva": "10",
        },
    )
    assert r.status_code == 400
    assert "sumar exactamente 100" in r.text
    assert get_politica(activo_actual()["id"]) is None


def test_politica_rechaza_tarifa_fuera_de_rango(client):
    r = client.post(
        "/config/politica",
        data={
            "porcentaje_libre": "40",
            "porcentaje_reinversion": "40",
            "porcentaje_reserva": "20",
            "calcular_impuesto": "1",
            "tarifa_marginal_actual": "45",
        },
    )
    assert r.status_code == 400
    assert get_politica(activo_actual()["id"]) is None


def test_politica_sin_calcular_impuesto_guarda_tarifa_cero(client):
    client.post(
        "/config/politica",
        data={
            "porcentaje_libre": "40",
            "porcentaje_reinversion": "40",
            "porcentaje_reserva": "20",
            "tarifa_marginal_actual": "19",
        },
        follow_redirects=False,
    )
    pol = get_politica(activo_actual()["id"])
    assert pol["calcular_impuesto"] == 0
    assert pol["tarifa_marginal_actual"] == 0.0


def test_capex_se_agrega_y_se_elimina(client):
    activo_id = activo_actual()["id"]
    r = client.post(
        "/config/capex",
        data={
            "concepto": "Amoblado zonas comunes",
            "monto": "12000000",
            "fecha": "2026-02-15",
            "horizonte_meses": "60",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    filas = get_capex(activo_id)
    assert len(filas) == 1
    assert filas[0]["concepto"] == "Amoblado zonas comunes"

    capex_id = filas[0]["id"]
    client.post(f"/config/capex/{capex_id}/eliminar", follow_redirects=False)
    assert get_capex(activo_id) == []


def test_capex_horizonte_sugerido_toma_la_vigencia_del_contrato(client):
    _guardar_contrato(client, vigencia_meses="48")
    r = client.get("/config/capex")
    assert 'value="48"' in r.text


def test_capex_rechaza_monto_no_numerico(client):
    r = client.post(
        "/config/capex",
        data={"concepto": "X", "monto": "abc", "fecha": "2026-02-15", "horizonte_meses": "60"},
    )
    assert r.status_code == 400
    assert get_capex(activo_actual()["id"]) == []
