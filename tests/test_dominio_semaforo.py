"""Tarea 10: diagnóstico del semáforo, determinístico."""
import pytest

from db.init_db import drop_all, init_db
from dominio.diagnostico import diagnostico_mes
from dominio.semaforo import (
    AMARILLO,
    ROJO,
    VERDE,
    calcular_ocupacion_equilibrio,
    semaforo_ocupacion,
    semaforo_resultado,
)
from tests.apoyo import activo_actual, nuevo_cliente


def test_ocupacion_equilibrio():
    # (3.000.000 + 300.000) / (900.000 * 0,9) = 4,07 -> 5
    assert calcular_ocupacion_equilibrio(3_000_000, 300_000, 900_000, 10) == 5
    assert calcular_ocupacion_equilibrio(3_000_000, 0, 0, 10) == 0


def test_semaforo_resultado_tres_colores():
    rojo = semaforo_resultado(-100, 1_000_000, 400_000, 50)
    assert rojo.estado == ROJO and "-100" in rojo.explicacion

    verde = semaforo_resultado(500_000, 4_000_000, 1_000_000, 50)  # 25%
    assert verde.estado == VERDE
    assert "25%" in verde.explicacion and "500,000" in verde.explicacion

    amarillo = semaforo_resultado(500_000, 1_000_000, 600_000, 50)  # 60%
    assert amarillo.estado == AMARILLO and "60%" in amarillo.explicacion


def test_semaforo_ocupacion_tres_colores_y_vacancia():
    vac = semaforo_ocupacion(2, 5, 4, 4, meses_bajo_equilibrio=3, meses_para_rojo=2)
    assert vac.estado == ROJO and "3 meses" in vac.explicacion

    bajo = semaforo_ocupacion(2, 5, 4, 4, meses_bajo_equilibrio=1, meses_para_rojo=3)
    assert bajo.estado == ROJO and "equilibrio de 4" in bajo.explicacion

    verde = semaforo_ocupacion(5, 5, 4, 4, meses_bajo_equilibrio=0, meses_para_rojo=3)
    assert verde.estado == VERDE

    amarillo = semaforo_ocupacion(4, 5, 5, 4, meses_bajo_equilibrio=0, meses_para_rojo=3)
    assert amarillo.estado == AMARILLO and "mínimo verde de 5" in amarillo.explicacion


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = nuevo_cliente()
    c.post(
        "/config/activo",
        data={"nombre": "C", "tipo": "coliving", "unidades_totales": "5",
              "comision_administrador_pct": "10", "moneda": "COP"},
        follow_redirects=False,
    )
    c.post(
        "/config/contrato",
        data={"canon_mensual": "3000000", "fecha_inicio": "2026-01-01",
              "fecha_vencimiento": "2031-01-01", "vigencia_meses": "60", "ventana_preaviso_dias": "90"},
        follow_redirects=False,
    )
    c.post(
        "/config/umbrales",
        data={"ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "50",
              "meses_consecutivos_baja_ocupacion_para_rojo": "2",
              "arriendo_promedio_unidad": "900000", "ventana_aviso_recordatorio_dias": "30"},
        follow_redirects=False,
    )
    return c


def _mes(client, mes, arrendadas):
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "300000",
            "gastos_variables": "100000", "comision_admin": "450000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    return client.post("/registro", data=data, follow_redirects=False)


def test_mes_lleno_da_verde_verde(client):
    _mes(client, 1, 5)
    d = diagnostico_mes(activo_actual()["id"], 2026, 1)
    assert d.ocupacion_equilibrio == 5
    assert d.resultado.estado == VERDE
    assert d.ocupacion.estado == VERDE


def test_dos_meses_bajo_equilibrio_disparan_vacancia(client):
    _mes(client, 1, 5)
    _mes(client, 2, 2)
    _mes(client, 3, 2)
    d3 = diagnostico_mes(activo_actual()["id"], 2026, 3)
    assert d3.ocupacion.estado == ROJO
    assert "2 meses" in d3.ocupacion.explicacion
    assert d3.resultado.estado == ROJO
    d1 = diagnostico_mes(activo_actual()["id"], 2026, 1)
    assert d1.ocupacion.estado == VERDE


def test_historico_muestra_los_puntos_de_diagnostico(client):
    _mes(client, 1, 5)
    r = client.get("/historico")
    assert "Diagnóstico" in r.text
    assert "dot--verde" in r.text
    assert "equil. 5" in r.text
