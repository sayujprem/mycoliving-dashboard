"""Tarea 6: motor del resultado del mes y vista consolidada."""
from pathlib import Path

import pytest

from db.init_db import drop_all, init_db
from motor.resultado import calcular_resultado, consolidar
from tests.apoyo import nuevo_cliente


def test_calcular_resultado_con_datos_no_inmobiliarios():
    # Un puesto de jugos: vende 1.000, sin comisión, 50 de insumos fijos, 30 variables,
    # y 400 de alquiler del local (obligación fija del periodo).
    assert calcular_resultado(
        ingreso=1000, comision=0, gastos_fijos=50, gastos_variables=30, obligacion_fija=400
    ) == 520


def test_calcular_resultado_puede_ser_negativo():
    assert calcular_resultado(
        ingreso=300, comision=30, gastos_fijos=100, gastos_variables=0, obligacion_fija=400
    ) == -230


def test_consolidar_conserva_el_orden_y_calcula_por_periodo():
    periodos = [
        {"anio": 2026, "mes": 6, "ingreso": 1000, "comision": 100, "gastos_fijos": 50, "gastos_variables": 30},
        {"anio": 2026, "mes": 7, "ingreso": 400, "comision": 40, "gastos_fijos": 50, "gastos_variables": 10},
    ]
    filas = consolidar(periodos, obligacion_fija=500)
    assert [(f.anio, f.mes) for f in filas] == [(2026, 6), (2026, 7)]
    assert filas[0].costos_variables == 180
    assert filas[0].resultado == 1000 - 180 - 500  # 320
    assert filas[1].resultado == 400 - 100 - 500  # -200


def test_modulo_motor_no_menciona_el_dominio():
    texto = (Path(__file__).resolve().parent.parent / "motor" / "resultado.py").read_text(encoding="utf-8").lower()
    for palabra in ("coliving", "inmueble", "subarriendo", "arriendo", "colombia", "canon"):
        assert palabra not in texto, f"'{palabra}' no debería estar en el módulo motor"


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
    return c


def _mes(client, mes, ingreso_por_unidad, arrendadas):
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "600000",
            "gastos_variables": "300000", "comision_admin": "700000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = str(ingreso_por_unidad)
    return client.post("/registro", data=data, follow_redirects=False)


def test_historico_muestra_resultado_con_canon_descontado(client):
    _mes(client, 6, 900000, 4)  # ingreso 3.600.000
    _mes(client, 7, 900000, 2)  # ingreso 1.800.000
    r = client.get("/historico")
    assert r.status_code == 200
    assert "Canon maestro" in r.text
    assert "Resultado" in r.text
    # mes 6: 3.600.000 - (700.000+600.000+300.000) - 3.000.000 = -1.000.000
    assert "-1,000,000" in r.text
    # mes 7: 1.800.000 - 1.600.000 - 3.000.000 = -2.800.000
    assert "-2,800,000" in r.text
