"""Si falla la generación de asesoría, el error se pinta donde se pulsó el botón.

Antes el POST siempre redirigía al histórico, aunque el botón estuviera en el panel: el
usuario terminaba en otra pantalla sin entender por qué.

No hace falta simular el API: conftest.py deja ANTHROPIC_API_KEY vacía, así que la
generación falla de forma determinista con "No hay ANTHROPIC_API_KEY configurada."
"""
import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from main import app


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
    data = {"mes": "7", "anio": "2026", "gastos_fijos": "2500000",
            "gastos_variables": "150000", "comision_admin": "360000", "novedades": ""}
    for i in range(1, 5):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    c.post("/registro", data=data, follow_redirects=False)
    return c


def test_error_desde_el_panel_vuelve_al_panel(client):
    r = client.post("/asesoria/2026/7", data={"origen": "panel"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/?anio=2026&mes=7&error_asesoria=")


def test_error_desde_el_historico_sigue_yendo_al_historico(client):
    r = client.post("/asesoria/2026/7", data={"origen": "historico"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/historico?error_asesoria=")


def test_sin_origen_el_destino_por_defecto_es_el_historico(client):
    """Cualquier POST que no mande el campo conserva el comportamiento anterior."""
    r = client.post("/asesoria/2026/7", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/historico?error_asesoria=")


def test_el_panel_pinta_el_error_y_deja_reintentar(client):
    r = client.post("/asesoria/2026/7", data={"origen": "panel"}, follow_redirects=False)
    pagina = client.get(r.headers["location"])
    assert pagina.status_code == 200
    assert "No se pudo generar la asesoría" in pagina.text
    assert "No hay ANTHROPIC_API_KEY" in pagina.text
    assert "alert--error-oscuro" in pagina.text
    # El botón sigue ahí: se puede reintentar sin salir del panel.
    assert "Generar asesoría" in pagina.text


def test_el_formulario_del_panel_declara_su_origen(client):
    html = client.get("/").text
    assert 'name="origen"' in html
    assert 'value="panel"' in html


def test_el_panel_sin_error_no_pinta_la_alerta(client):
    html = client.get("/").text
    assert "alert--error-oscuro" not in html
    assert "No se pudo generar la asesoría" not in html
