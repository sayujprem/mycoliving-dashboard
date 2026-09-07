"""Tarea 9: motor de recordatorios por fecha."""
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_recordatorios, set_configuracion
from dominio.recordatorios import clasificar_recordatorios
from main import app
from motor.recordatorios import AL_DIA, PROXIMO, VENCIDO, clasificar, proxima_fecha, sumar_meses


def test_sumar_meses_ajusta_el_dia_al_fin_de_mes():
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert sumar_meses(date(2026, 1, 15), 13) == date(2027, 2, 15)


def test_proxima_fecha_periodica_y_fija():
    assert proxima_fecha(date(2026, 1, 1), 6, None) == date(2026, 7, 1)
    assert proxima_fecha(None, None, date(2026, 5, 1)) == date(2026, 5, 1)


def test_proxima_fecha_sin_datos_falla():
    with pytest.raises(ValueError):
        proxima_fecha(None, None, None)


def test_clasificar_tres_estados():
    hoy = date(2026, 1, 20)
    assert clasificar(date(2026, 1, 10), hoy, 30).estado == VENCIDO
    assert clasificar(date(2026, 1, 10), hoy, 30).dias_restantes == -10
    assert clasificar(date(2026, 2, 5), hoy, 30).estado == PROXIMO
    assert clasificar(date(2026, 6, 1), hoy, 30).estado == AL_DIA


def test_modulo_motor_recordatorios_sin_dominio():
    texto = (Path(__file__).resolve().parent.parent / "motor" / "recordatorios.py").read_text(encoding="utf-8").lower()
    for palabra in ("coliving", "inmueble", "subarriendo", "arriendo", "colombia", "canon", "poliza"):
        assert palabra not in texto


def test_clasifica_seguro_periodico_y_contrato_fijo():
    hoy = date(2026, 8, 1)
    recordatorios = [
        {  # seguro periódico: última hace ~12 meses, vence 22-ago-2026 -> próximo
            "id": 1, "categoria": "seguro", "descripcion": "Póliza",
            "ultima_fecha": "2025-08-22", "frecuencia_meses": 12,
            "fecha_vencimiento_fija": None, "proxima_fecha": "2026-08-22",
        },
        {  # contrato con fecha fija ya pasada -> vencido
            "id": 2, "categoria": "contrato", "descripcion": "Renovación cláusula",
            "ultima_fecha": None, "frecuencia_meses": None,
            "fecha_vencimiento_fija": "2026-07-15", "proxima_fecha": "2026-07-15",
        },
    ]
    clasificados = clasificar_recordatorios(recordatorios, {"ventana_aviso_recordatorio_dias": "30"}, hoy=hoy)
    por_id = {f["id"]: e for f, e in clasificados}
    assert por_id[1].estado == PROXIMO
    assert por_id[1].dias_restantes == 21
    assert por_id[2].estado == VENCIDO
    # el vencido va primero (ordenado por urgencia)
    assert clasificados[0][0]["id"] == 2


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = TestClient(app)
    c.post(
        "/config/activo",
        data={"nombre": "C", "tipo": "coliving", "unidades_totales": "5",
              "comision_administrador_pct": "10", "moneda": "COP"},
        follow_redirects=False,
    )
    return c


def test_alta_de_recordatorio_periodico_calcula_proxima_fecha(client):
    r = client.post(
        "/config/recordatorios",
        data={"categoria": "seguro", "descripcion": "Póliza de arrendamiento",
              "ultima_fecha": "2026-01-10", "frecuencia_meses": "12"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    recs = get_recordatorios(get_activo()["id"])
    assert len(recs) == 1
    assert recs[0]["proxima_fecha"] == "2027-01-10"


def test_recordatorio_sin_frecuencia_ni_fecha_fija_se_rechaza(client):
    r = client.post(
        "/config/recordatorios",
        data={"categoria": "contrato", "descripcion": "X"},
    )
    assert r.status_code == 400
    assert get_recordatorios(get_activo()["id"]) == []


def test_categorias_salen_de_configuracion(client):
    set_configuracion(get_activo()["id"], "categorias_recordatorio", "mantenimiento, seguro, contrato")
    r = client.get("/config/recordatorios")
    assert '<option value="mantenimiento">' in r.text
    assert '<option value="contrato">' in r.text
