"""Tarea 8: recuperación del capex."""
from datetime import date
from pathlib import Path

import pytest

from db.init_db import drop_all, init_db
from dominio.capex import resumen_capex
from motor.capex import recuperacion
from tests.apoyo import nuevo_cliente


def test_recuperacion_a_mitad_de_horizonte():
    r = recuperacion(1_000_000, horizonte_meses=60, meses_transcurridos=30)
    assert r.recuperado == 500_000
    assert r.pct_recuperado == 50.0
    assert r.pendiente == 500_000
    assert r.completado is False


def test_recuperacion_nunca_pasa_de_100():
    r = recuperacion(1_000_000, horizonte_meses=60, meses_transcurridos=72)
    assert r.recuperado == 1_000_000
    assert r.pct_recuperado == 100.0
    assert r.completado is True


def test_recuperacion_al_inicio_es_cero():
    r = recuperacion(1_000_000, horizonte_meses=60, meses_transcurridos=0)
    assert r.recuperado == 0
    assert r.pct_recuperado == 0.0


def test_recuperacion_con_horizonte_cero_esta_completa():
    r = recuperacion(500_000, horizonte_meses=0, meses_transcurridos=1)
    assert r.completado is True


def test_modulo_motor_capex_sin_vocabulario_de_dominio():
    texto = (Path(__file__).resolve().parent.parent / "motor" / "capex.py").read_text(encoding="utf-8").lower()
    for palabra in ("coliving", "inmueble", "subarriendo", "arriendo", "colombia", "canon", "zonas comunes"):
        assert palabra not in texto


def test_resumen_capex_agrega_varias_partidas():
    partidas = [
        {"id": 1, "concepto": "A", "monto": 1_000_000, "fecha": "2026-01-01", "horizonte_meses": 60},
        {"id": 2, "concepto": "B", "monto": 500_000, "fecha": "2026-01-01", "horizonte_meses": 10},
    ]
    res = resumen_capex(partidas, hasta=date(2026, 7, 1))  # 6 meses después
    assert res.monto_total == 1_500_000
    assert res.recuperado == pytest.approx(1_000_000 * 0.1 + 500_000 * 0.6)  # 100k + 300k
    assert res.pct_recuperado == pytest.approx(400_000 / 1_500_000 * 100)


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
    return c


def test_config_capex_muestra_recuperacion(client):
    client.post(
        "/config/capex",
        data={"concepto": "Amoblado", "monto": "12000000", "fecha": "2020-01-01", "horizonte_meses": "12"},
        follow_redirects=False,
    )
    r = client.get("/config/capex")
    assert r.status_code == 200
    assert "Recuperación total" in r.text
    assert "100 %" in r.text  # 2020 + 12 meses ya pasó
