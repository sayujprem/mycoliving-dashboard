"""Tareas 16 y 17: datos de arranque y recordatorio externo documentado."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_configuracion, get_politica
from main import app
from scripts.seed_coliving import seed

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _db_limpia():
    drop_all()
    init_db()


def test_seed_deja_el_activo_precargado():
    seed()
    activo = get_activo()
    assert activo is not None
    assert activo["unidades_totales"] == 5
    assert activo["comision_administrador_pct"] == 10.0
    assert "Armenia" in activo["ubicacion"]
    conf = get_configuracion(activo["id"])
    assert conf["ocupacion_minima_verde"] == "4"
    assert "seguro" in conf["categorias_recordatorio"]
    assert get_politica(activo["id"]) is not None


def test_seed_es_idempotente():
    seed()
    primer_id = get_activo()["id"]
    seed()  # segunda corrida no debe duplicar ni pisar
    from db.connection import get_connection

    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS n FROM activo").fetchone()["n"]
    conn.close()
    assert n == 1
    assert get_activo()["id"] == primer_id


def test_app_arranca_con_el_activo_precargado():
    seed()
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "Coliving Granada" in r.text
    assert "Todavía no hay un activo configurado" not in r.text


def test_readme_documenta_el_recordatorio_mensual():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "Recordatorio mensual de carga" in readme
    assert "evento recurrente de calendario" in readme
    assert "/registro" in readme


def test_readme_documenta_el_seed_y_el_arranque():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "python -m scripts.seed_coliving" in readme
    assert "uvicorn main:app" in readme
    assert "ANTHROPIC_API_KEY" in readme
