"""Tarea 1: la app levanta y sirve la pagina base."""
from pathlib import Path

import pytest

from db.init_db import drop_all, init_db
from main import app
from tests.apoyo import ClienteConSesion, nuevo_cliente


@pytest.fixture(scope="module", autouse=True)
def _base():
    drop_all()
    init_db()


def test_sin_sesion_el_inicio_manda_a_entrar():
    resp = ClienteConSesion(app).get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/entrar"


def test_index_responde_ok_con_sesion():
    resp = nuevo_cliente().get("/")
    assert resp.status_code == 200
    assert "My Coliving Dashboard" in resp.text


def test_shell_v2_carga_fuentes_hoja_de_estilo_y_script():
    resp = nuevo_cliente().get("/")
    assert 'href="/static/app.css"' in resp.text
    assert 'src="/static/app.js"' in resp.text
    assert "Manrope" in resp.text
    assert 'class="app-nav"' in resp.text


def test_la_pantalla_de_acceso_no_muestra_la_navegacion():
    resp = ClienteConSesion(app).get("/entrar")
    assert resp.status_code == 200
    assert 'class="app-nav"' not in resp.text


def test_static_app_css_se_sirve_sin_sesion():
    resp = ClienteConSesion(app).get("/static/app.css")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/css")
    assert "--accent: #D0FD65" in resp.text


def test_ninguna_plantilla_usa_javascript_en_linea():
    """La politica de seguridad prohibe scripts en linea: un onclick no se ejecutaria
    y, en el caso de una confirmacion, el formulario se enviaria sin preguntar."""
    plantillas = Path(__file__).resolve().parent.parent / "web" / "templates"
    for p in plantillas.glob("*.html"):
        html = p.read_text(encoding="utf-8")
        for prohibido in ("onclick=", "onsubmit=", "onchange=", "<script>", "javascript:"):
            assert prohibido not in html, f"{p.name} usa {prohibido}"


def test_carpetas_motor_y_dominio_tienen_frontera_documentada():
    raiz = Path(__file__).resolve().parent.parent
    motor_readme = (raiz / "motor" / "README.md").read_text(encoding="utf-8")
    dominio_readme = (raiz / "dominio" / "README.md").read_text(encoding="utf-8")
    assert "independiente del tipo de activo" in motor_readme
    assert "Colombia" in dominio_readme
