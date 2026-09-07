"""Tarea 1: la app levanta y sirve la pagina base."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_index_responde_ok():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MyColiving Dashboard" in resp.text


def test_shell_v2_carga_fuentes_y_hoja_de_estilo():
    resp = client.get("/")
    assert 'href="/static/app.css"' in resp.text
    assert "Manrope" in resp.text
    assert 'class="app-nav"' in resp.text


def test_static_app_css_se_sirve():
    resp = client.get("/static/app.css")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/css")
    assert "--accent: #D0FD65" in resp.text


def test_carpetas_motor_y_dominio_tienen_frontera_documentada():
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    motor_readme = (raiz / "motor" / "README.md").read_text(encoding="utf-8")
    dominio_readme = (raiz / "dominio" / "README.md").read_text(encoding="utf-8")
    assert "independiente del tipo de activo" in motor_readme
    assert "Colombia" in dominio_readme
