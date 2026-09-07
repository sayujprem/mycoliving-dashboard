"""Datos de ejemplo: el dashboard completo sin cifras reales, y borrable de un golpe."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import (
    get_activo,
    get_capex,
    get_configuracion,
    get_recordatorios,
    get_reportes,
    get_reserva_movimientos,
)
from dominio.configuracion import ventana_aviso
from dominio.demo import cargar_demo, estado_demo, limpiar_demo, meses_demo
from dominio.diagnostico import diagnostico_mes
from dominio.recordatorios import clasificar_recordatorios
from main import app
from motor.recordatorios import AL_DIA, PROXIMO, VENCIDO
from scripts.seed_coliving import seed


@pytest.fixture
def client():
    drop_all()
    init_db()
    seed()
    return TestClient(app)


@pytest.fixture
def activo_id(client):
    return get_activo()["id"]


def test_cargar_demo_deja_seis_meses(activo_id):
    r = cargar_demo(activo_id)
    assert r["ok"] is True
    assert r["meses"] == 6
    assert len(get_reportes(activo_id)) == 6


def test_los_seis_meses_cubren_los_tres_colores(activo_id):
    """Blinda toda la aritmética del dataset. Si falla, lo que se mueve son los gastos
    variables del mes afectado, nunca el umbral."""
    cargar_demo(activo_id)
    resultado, ocupacion = set(), set()
    for anio, mes in meses_demo():
        d = diagnostico_mes(activo_id, anio, mes)
        assert d is not None
        resultado.add(d.resultado.estado)
        ocupacion.add(d.ocupacion.estado)
    assert resultado == {"verde", "amarillo", "rojo"}
    assert ocupacion == {"verde", "amarillo", "rojo"}


def test_la_reserva_termina_agotada(activo_id):
    cargar_demo(activo_id)
    movimientos = get_reserva_movimientos(activo_id)
    assert len(movimientos) == 6
    assert movimientos[-1]["saldo_resultante"] < 0


def test_el_ultimo_mes_dispara_la_regla_de_vacancia(activo_id):
    cargar_demo(activo_id)
    ultimo = meses_demo()[-1]
    d = diagnostico_mes(activo_id, *ultimo)
    assert d.ocupacion.estado == "rojo"
    assert "meses seguidos" in d.ocupacion.explicacion


def test_demo_carga_capex_y_tres_recordatorios_en_sus_tres_estados(activo_id):
    cargar_demo(activo_id)
    assert len(get_capex(activo_id)) == 2

    recordatorios = get_recordatorios(activo_id)
    assert len(recordatorios) == 3
    conf = get_configuracion(activo_id)
    estados = [e.estado for _, e in clasificar_recordatorios(recordatorios, conf)]
    assert sorted(estados) == sorted([VENCIDO, PROXIMO, AL_DIA])
    assert ventana_aviso(conf) == 30


def test_demo_marca_el_estado_sin_ensuciar_la_ui(client, activo_id):
    cargar_demo(activo_id)
    conf = get_configuracion(activo_id)
    assert conf["demo_cargado"] == date.today().isoformat()
    assert len(conf["demo_meses"].split(",")) == 6
    # Las claves no están en CLAVES_CONFIGURACION, así que no se filtran a la interfaz.
    assert "demo_cargado" not in client.get("/config").text
    assert "demo_meses" not in client.get("/config/umbrales").text


def test_el_banner_aparece_en_el_panel(client, activo_id):
    cargar_demo(activo_id)
    html = client.get("/").text
    assert "banner-demo" in html
    assert "Datos de ejemplo" in html


def test_limpiar_demo_borra_todo_lo_que_cargo(activo_id):
    cargar_demo(activo_id)
    r = limpiar_demo(activo_id)
    assert r["ok"] is True
    assert (r["meses"], r["capex"], r["recordatorios"]) == (6, 2, 3)
    assert get_reportes(activo_id) == []
    assert get_capex(activo_id) == []
    assert get_recordatorios(activo_id) == []
    assert get_reserva_movimientos(activo_id) == []
    assert "demo_cargado" not in get_configuracion(activo_id)


def test_limpiar_demo_no_toca_datos_reales(client, activo_id):
    """La guarda que importa: quitar la demo no puede llevarse por delante lo que
    el usuario cargó a mano."""
    cargar_demo(activo_id)

    # Un mes real, fuera de la lista de meses de la demo.
    real = {"mes": "1", "anio": "2020", "gastos_fijos": "2500000",
            "gastos_variables": "100000", "comision_admin": "360000", "novedades": "real"}
    for i in range(1, 5):
        real[f"unidad_{i}_arrendada"] = "1"
        real[f"unidad_{i}_ingreso"] = "900000"
    client.post("/registro", data=real, follow_redirects=False)
    client.post("/config/capex", data={"concepto": "Reforma del baño 3", "monto": "3000000",
                "fecha": "2020-01-15", "horizonte_meses": "60"}, follow_redirects=False)

    limpiar_demo(activo_id)

    reportes = get_reportes(activo_id)
    assert len(reportes) == 1
    assert (reportes[0]["anio"], reportes[0]["mes"]) == (2020, 1)
    capex = get_capex(activo_id)
    assert len(capex) == 1
    assert capex[0]["concepto"] == "Reforma del baño 3"
    # La reserva se rehízo sobre el mes real que quedó.
    assert len(get_reserva_movimientos(activo_id)) == 1


def test_limpiar_sin_demo_cargada_no_borra_nada(client, activo_id):
    real = {"mes": "1", "anio": "2020", "gastos_fijos": "2500000",
            "gastos_variables": "100000", "comision_admin": "360000", "novedades": "real"}
    for i in range(1, 5):
        real[f"unidad_{i}_arrendada"] = "1"
        real[f"unidad_{i}_ingreso"] = "900000"
    client.post("/registro", data=real, follow_redirects=False)

    r = limpiar_demo(activo_id)
    assert r["ok"] is False
    assert r["meses"] == 0
    assert len(get_reportes(activo_id)) == 1


def test_cargar_demo_se_niega_si_ya_hay_meses(client, activo_id):
    real = {"mes": "1", "anio": "2020", "gastos_fijos": "2500000",
            "gastos_variables": "100000", "comision_admin": "360000", "novedades": "real"}
    for i in range(1, 5):
        real[f"unidad_{i}_arrendada"] = "1"
        real[f"unidad_{i}_ingreso"] = "900000"
    client.post("/registro", data=real, follow_redirects=False)

    r = cargar_demo(activo_id)
    assert r["ok"] is False
    assert "no se mezcla" in r["error"]
    assert len(get_reportes(activo_id)) == 1


def test_el_banner_desaparece_tras_limpiar_desde_la_interfaz(client, activo_id):
    cargar_demo(activo_id)
    r = client.post("/demo/limpiar", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert estado_demo(activo_id) is None
    assert "Datos de ejemplo" not in client.get("/").text


def test_seed_y_demo_conviven(activo_id):
    """El seed son datos de arranque real; la demo es movimiento de ejemplo."""
    cargar_demo(activo_id)
    seed()  # idempotente: no debe pisar ni duplicar
    assert get_activo()["id"] == activo_id
    assert len(get_reportes(activo_id)) == 6


def test_el_arriendo_de_la_demo_coincide_con_el_del_seed(activo_id):
    """Si se desalinean, la ocupación de equilibrio cambia y el mes amarillo se cae a rojo
    sin que nada más falle. Ya pasó una vez."""
    from dominio.demo import ARRIENDO_UNIDAD

    conf = get_configuracion(activo_id)
    assert float(conf["arriendo_promedio_unidad"]) == float(ARRIENDO_UNIDAD)


def test_los_meses_demo_terminan_el_mes_pasado():
    """Anclados a hoy para que la demo no se vea rancia dentro de un año."""
    meses = meses_demo(date(2026, 3, 15))
    assert len(meses) == 6
    assert meses[-1] == (2026, 2)
    assert meses[0] == (2025, 9)
