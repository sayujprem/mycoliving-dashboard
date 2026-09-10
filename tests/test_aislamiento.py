"""Aislamiento entre cuentas: nadie ve ni toca los datos de otro.

Son las pruebas que mas importan de toda la suite. Cada una hace que una cuenta
intente, por un camino distinto, alcanzar los datos de otra.
"""
import pytest

from db.connection import db_cursor, fijar_usuario
from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_activo_por_id, get_capex, get_recordatorios
from db.usuarios import get_usuario_por_email
from tests.apoyo import nuevo_cliente

ANA = "ana@ejemplo.com"
BETO = "beto@ejemplo.com"


def _activo(cliente, nombre):
    cliente.post("/config/activo", data={"nombre": nombre, "tipo": "coliving", "unidades_totales": "3",
                 "comision_administrador_pct": "10", "moneda": "COP"})


def _mes(cliente, mes=7):
    cliente.post("/registro", data={"anio": "2026", "mes": str(mes), "gastos_fijos": "1000000",
                 "gastos_variables": "0", "comision_admin": "0", "novedades": "confidencial de Ana",
                 "unidad_1_arrendada": "1", "unidad_1_ingreso": "900000"})


def _id(email):
    return get_usuario_por_email(email)["id"]


@pytest.fixture
def ana_y_beto():
    drop_all()
    init_db()
    ana = nuevo_cliente(ANA)
    _activo(ana, "Coliving de Ana")
    _mes(ana)
    ana.post("/config/capex", data={"concepto": "Sofá de Ana", "monto": "2000000",
             "fecha": "2026-01-15", "horizonte_meses": "24"})
    ana.post("/config/recordatorios", data={"categoria": "seguro", "descripcion": "Póliza de Ana",
             "ultima_fecha": "2026-01-10", "frecuencia_meses": "12"})
    beto = nuevo_cliente(BETO)
    _activo(beto, "Coliving de Beto")
    return ana, beto


def _datos_de_ana():
    fijar_usuario(_id(ANA))
    activo = get_activo(_id(ANA))
    return activo, get_capex(activo["id"]), get_recordatorios(activo["id"])


def test_cada_cuenta_ve_solo_su_activo(ana_y_beto):
    ana, beto = ana_y_beto
    assert "Coliving de Ana" in ana.get("/").text
    panel_beto = beto.get("/").text
    assert "Coliving de Beto" in panel_beto
    assert "Coliving de Ana" not in panel_beto


def test_el_historico_de_beto_no_muestra_meses_de_ana(ana_y_beto):
    _, beto = ana_y_beto
    html = beto.get("/historico").text
    assert "Todavía no hay meses registrados" in html


def test_beto_no_llega_al_mes_de_ana_por_url_directa(ana_y_beto):
    _, beto = ana_y_beto
    # Las URL no llevan el activo: /registro?anio=2026&mes=7 es "mi julio", no el de Ana.
    html = beto.get("/registro?anio=2026&mes=7").text
    assert "confidencial de Ana" not in html
    r = beto.get("/asesoria/2026/7", follow_redirects=False)
    assert r.headers["location"] == "/historico"


def test_beto_no_puede_borrar_el_capex_de_ana_adivinando_el_id(ana_y_beto):
    _, beto = ana_y_beto
    _, capex, _ = _datos_de_ana()
    beto.post(f"/config/capex/{capex[0]['id']}/eliminar")
    _, capex_despues, _ = _datos_de_ana()
    assert len(capex_despues) == 1


def test_beto_no_puede_borrar_un_recordatorio_de_ana_adivinando_el_id(ana_y_beto):
    _, beto = ana_y_beto
    _, _, recs = _datos_de_ana()
    beto.post(f"/config/recordatorios/{recs[0]['id']}/eliminar")
    _, _, recs_despues = _datos_de_ana()
    assert len(recs_despues) == 1


def test_beto_no_puede_borrar_el_mes_de_ana(ana_y_beto):
    ana, beto = ana_y_beto
    beto.post("/historico/2026/7/eliminar")
    assert "confidencial de Ana" in ana.get("/registro?anio=2026&mes=7").text


def test_guardar_el_activo_de_beto_no_toca_el_de_ana(ana_y_beto):
    _, beto = ana_y_beto
    _activo(beto, "Beto renombrado")
    activo_ana, _, _ = _datos_de_ana()
    assert activo_ana["nombre"] == "Coliving de Ana"


def test_la_base_rechaza_la_fuga_aunque_el_codigo_la_pida(ana_y_beto):
    """Segunda capa: si una ruta olvidara filtrar, RLS igual niega la fila."""
    activo_ana, _, _ = _datos_de_ana()
    fijar_usuario(_id(BETO))
    assert get_activo_por_id(activo_ana["id"]) is None
    assert get_capex(activo_ana["id"]) == []
    with db_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM reporte_mensual")
        assert cur.fetchone()["n"] == 0  # Beto no tiene meses; los de Ana no cuentan


def test_sin_cuenta_fijada_la_base_no_devuelve_nada(ana_y_beto):
    fijar_usuario(None)
    with db_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM activo")
        assert cur.fetchone()["n"] == 0
