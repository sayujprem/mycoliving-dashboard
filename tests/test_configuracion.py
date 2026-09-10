"""Tarea 3: configuración del activo y de los umbrales de dominio."""
import pytest

from db.init_db import drop_all, init_db
from db.repositorio import get_configuracion
from tests.apoyo import activo_actual, nuevo_cliente


@pytest.fixture
def client():
    drop_all()
    init_db()
    return nuevo_cliente()


def _alta_activo(client):
    return client.post(
        "/config/activo",
        data={
            "nombre": "Coliving Granada",
            "tipo": "coliving",
            "unidades_totales": "5",
            "comision_administrador_pct": "10",
            "moneda": "COP",
            "ubicacion": "Armenia",
            "notas": "5 apartaestudios con baño privado",
        },
        follow_redirects=False,
    )


def test_sin_activo_config_redirige_al_alta(client):
    r = client.get("/config", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/config/activo"


def test_crear_activo_persiste(client):
    r = _alta_activo(client)
    assert r.status_code == 303
    activo = activo_actual()
    assert activo["nombre"] == "Coliving Granada"
    assert activo["unidades_totales"] == 5
    assert activo["comision_administrador_pct"] == 10.0


def test_editar_activo_no_crea_uno_nuevo(client):
    _alta_activo(client)
    client.post(
        "/config/activo",
        data={
            "nombre": "Coliving Granada",
            "tipo": "coliving",
            "unidades_totales": "6",
            "comision_administrador_pct": "10",
            "moneda": "COP",
        },
        follow_redirects=False,
    )
    from db.connection import get_connection

    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS n FROM activo").fetchone()["n"]
    conn.close()
    assert n == 1
    assert activo_actual()["unidades_totales"] == 6


def test_activo_rechaza_unidades_invalidas(client):
    r = client.post(
        "/config/activo",
        data={
            "nombre": "X",
            "tipo": "coliving",
            "unidades_totales": "0",
            "comision_administrador_pct": "10",
            "moneda": "COP",
        },
    )
    assert r.status_code == 400
    assert "mayor que cero" in r.text
    assert activo_actual() is None


def test_editar_umbrales_persiste(client):
    _alta_activo(client)
    activo_id = activo_actual()["id"]
    r = client.post(
        "/config/umbrales",
        data={
            "ocupacion_minima_verde": "4",
            "gasto_maximo_pct_verde": "50",
            "meses_consecutivos_baja_ocupacion_para_rojo": "2",
            "arriendo_promedio_unidad": "850000",
            "ventana_aviso_recordatorio_dias": "30",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    conf = get_configuracion(activo_id)
    assert conf["ocupacion_minima_verde"] == "4"
    assert conf["arriendo_promedio_unidad"] == "850000"


def test_umbrales_rechaza_valor_no_numerico(client):
    _alta_activo(client)
    r = client.post("/config/umbrales", data={"ocupacion_minima_verde": "abc"})
    assert r.status_code == 400
    assert "debe ser un número" in r.text


def test_umbrales_ignora_campos_vacios(client):
    _alta_activo(client)
    activo_id = activo_actual()["id"]
    client.post("/config/umbrales", data={"ocupacion_minima_verde": "4"}, follow_redirects=False)
    conf = get_configuracion(activo_id)
    assert conf == {"ocupacion_minima_verde": "4"}
