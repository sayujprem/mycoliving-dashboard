"""Tarea 15: estado "primer mes / sin histórico"."""
import pytest

from db.init_db import drop_all, init_db
from dominio.diagnostico import diagnostico_mes
from tests.apoyo import activo_actual, nuevo_cliente


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = nuevo_cliente()
    c.post("/config/activo", data={"nombre": "C", "tipo": "coliving", "unidades_totales": "5",
           "comision_administrador_pct": "10", "moneda": "COP"}, follow_redirects=False)
    c.post("/config/contrato", data={"canon_mensual": "3000000", "fecha_inicio": "2026-01-01",
           "fecha_vencimiento": "2031-01-01", "vigencia_meses": "60", "ventana_preaviso_dias": "90"},
           follow_redirects=False)
    c.post("/config/umbrales", data={"ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "50",
           "meses_consecutivos_baja_ocupacion_para_rojo": "2", "arriendo_promedio_unidad": "900000",
           "ventana_aviso_recordatorio_dias": "30"}, follow_redirects=False)
    return c


def _mes(client, mes, arrendadas):
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "300000",
            "gastos_variables": "100000", "comision_admin": "450000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    client.post("/registro", data=data, follow_redirects=False)


def test_un_solo_mes_deja_la_vacancia_en_espera(client):
    _mes(client, 7, 2)  # bajo el equilibrio
    d = diagnostico_mes(activo_actual()["id"], 2026, 7)
    assert d.vacancia_en_espera is True
    # está en rojo por estar bajo el equilibrio, pero NO por la regla de vacancia
    assert d.ocupacion.estado == "rojo"
    assert "meses seguidos" not in d.ocupacion.explicacion


def test_panel_avisa_que_es_el_primer_mes(client):
    _mes(client, 7, 3)
    html = client.get("/").text
    assert "Primer mes registrado" in html
    assert "Regla de vacancia: en espera" in html


def test_con_suficientes_meses_ya_no_esta_en_espera(client):
    _mes(client, 6, 2)
    _mes(client, 7, 2)
    d = diagnostico_mes(activo_actual()["id"], 2026, 7)
    assert d.vacancia_en_espera is False
    html = client.get("/").text
    assert "Primer mes registrado" not in html


def test_con_dos_meses_bajo_equilibrio_la_vacancia_si_dispara(client):
    _mes(client, 6, 2)
    _mes(client, 7, 2)
    d = diagnostico_mes(activo_actual()["id"], 2026, 7)
    assert d.ocupacion.estado == "rojo"
    assert "2 meses seguidos" in d.ocupacion.explicacion
