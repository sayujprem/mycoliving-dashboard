"""Tarea 7: brecha vs. política y trayectoria del fondo de reserva."""
from pathlib import Path

import pytest

from db.init_db import drop_all, init_db
from db.repositorio import get_reserva_movimientos
from motor.politica import calcular_brecha
from motor.reserva import meses_restantes, reserva_agotada, trayectoria
from tests.apoyo import activo_actual, nuevo_cliente

PCTS = (40.0, 40.0, 20.0)  # libre, reinversión, reserva


def test_brecha_mes_positivo_esta_en_linea():
    b = calcular_brecha(1000, *PCTS)
    assert b.en_linea is True
    assert b.meta_libre == 400
    assert b.porcentaje_libre_real == 40.0
    assert b.brecha_puntos == 0.0
    assert b.brecha_monto == 0.0


def test_brecha_mes_negativo_no_cubre_la_politica():
    b = calcular_brecha(-500, *PCTS)
    assert b.en_linea is False
    assert b.meta_libre == 0.0
    assert b.porcentaje_libre_real == 0.0
    assert b.brecha_puntos == -40.0
    assert b.brecha_monto == -500


def test_trayectoria_acumula_el_saldo():
    movs = trayectoria(
        [(2026, 1, 1000), (2026, 2, -500), (2026, 3, -800)], pct_reserva=20.0
    )
    assert [m.monto for m in movs] == [200.0, -500, -800]
    assert [m.saldo_resultante for m in movs] == [200.0, -300.0, -1100.0]


def test_meses_restantes_y_agotada():
    assert meses_restantes(1000, 400) == 2.5
    assert meses_restantes(1000, 0) is None
    assert meses_restantes(-100, 400) == 0.0
    assert reserva_agotada(-1) is True
    assert reserva_agotada(0) is True
    assert reserva_agotada(1) is False


def test_modulos_motor_sin_vocabulario_de_dominio():
    raiz = Path(__file__).resolve().parent.parent / "motor"
    for archivo in ("politica.py", "reserva.py"):
        texto = (raiz / archivo).read_text(encoding="utf-8").lower()
        for palabra in ("coliving", "inmueble", "subarriendo", "arriendo", "colombia", "canon"):
            assert palabra not in texto, f"'{palabra}' en motor/{archivo}"


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
        "/config/politica",
        data={"porcentaje_libre": "40", "porcentaje_reinversion": "40", "porcentaje_reserva": "20"},
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


def test_mes_positivo_hace_crecer_la_reserva(client):
    _mes(client, 1, 5)  # ingreso 4.5M; resultado = 4.5M - 450k - 400k - 3M = 650k
    movs = get_reserva_movimientos(activo_actual()["id"])
    assert len(movs) == 1
    assert movs[0]["monto"] == pytest.approx(130000.0)  # 650k * 20%
    assert movs[0]["saldo_resultante"] == pytest.approx(130000.0)
    r = client.get("/historico")
    assert "Fondo de reserva" in r.text
    assert "130,000" in r.text


def test_mes_negativo_consume_la_reserva_y_avisa(client):
    _mes(client, 1, 5)  # +130k
    _mes(client, 2, 2)  # ingreso 1.8M; resultado = 1.8M - 850k - 3M = -2.05M
    movs = get_reserva_movimientos(activo_actual()["id"])
    assert movs[-1]["monto"] == pytest.approx(-2050000.0)
    assert movs[-1]["saldo_resultante"] == pytest.approx(130000.0 - 2050000.0)
    r = client.get("/historico")
    assert "Reserva agotada" in r.text
    assert "no cubre la política" in r.text


def test_editar_politica_recalcula_la_reserva(client):
    _mes(client, 1, 5)  # con 20%: +130k
    client.post(
        "/config/politica",
        data={"porcentaje_libre": "40", "porcentaje_reinversion": "10", "porcentaje_reserva": "50"},
        follow_redirects=False,
    )
    movs = get_reserva_movimientos(activo_actual()["id"])
    assert movs[0]["monto"] == pytest.approx(325000.0)  # 650k * 50%
