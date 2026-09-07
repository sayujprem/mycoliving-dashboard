"""Tarea 14: vista del mes (dashboard)."""
import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo
from dominio.asesoria import generar_y_guardar
from dominio.panel import panel_mes
from main import app


class _Bloque:
    type = "tool_use"
    name = "entregar_asesoria"

    def __init__(self, entrada):
        self.input = entrada


class _ClienteOK:
    def __init__(self, entrada):
        self._r = type("R", (), {"content": [_Bloque(entrada)]})()
        self.messages = self

    def create(self, **kwargs):
        return self._r


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = TestClient(app)
    c.post("/config/activo", data={"nombre": "Coliving Granada", "tipo": "coliving",
           "unidades_totales": "5", "comision_administrador_pct": "10", "moneda": "COP",
           "ubicacion": "Armenia"}, follow_redirects=False)
    c.post("/config/contrato", data={"canon_mensual": "3000000", "fecha_inicio": "2026-01-01",
           "fecha_vencimiento": "2031-01-01", "vigencia_meses": "60", "ventana_preaviso_dias": "90"},
           follow_redirects=False)
    c.post("/config/politica", data={"porcentaje_libre": "40", "porcentaje_reinversion": "40",
           "porcentaje_reserva": "20"}, follow_redirects=False)
    c.post("/config/umbrales", data={"ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "50",
           "meses_consecutivos_baja_ocupacion_para_rojo": "2", "arriendo_promedio_unidad": "900000",
           "ventana_aviso_recordatorio_dias": "30"}, follow_redirects=False)
    c.post("/config/capex", data={"concepto": "Amoblado zonas comunes", "monto": "12000000",
           "fecha": "2026-01-15", "horizonte_meses": "60"}, follow_redirects=False)
    return c


def _mes(client, mes, arrendadas):
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "300000",
            "gastos_variables": "100000", "comision_admin": "450000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    client.post("/registro", data=data, follow_redirects=False)


def test_panel_sin_activo(client):
    drop_all()
    init_db()
    r = client.get("/")
    assert r.status_code == 200
    assert "Todavía no hay un activo configurado" in r.text


def test_panel_sin_historico(client):
    r = client.get("/")
    assert "Sin meses registrados" in r.text


def test_panel_mes_arma_las_piezas(client):
    _mes(client, 7, 5)
    datos = panel_mes(get_activo()["id"], 2026, 7)
    assert datos["diagnostico"] is not None
    assert datos["brecha"] is not None
    assert datos["consolidado"].resultado == pytest.approx(4_500_000 - 850_000 - 3_000_000)
    assert datos["asesoria"] is None


def test_panel_muestra_las_siete_piezas(client):
    _mes(client, 7, 5)
    r = client.get("/")
    for marca in ("Hacer", "Entender", "Decidir", "RECORDATORIOS", "SEMÁFORO",
                  "PANORAMA DEL MES", "BRECHA VS. POLÍTICA", "ASESORÍA", "CAPEX RECUPERADO",
                  "FONDO DE RESERVA", "HORIZONTE", "Contrato maestro"):
        assert marca in r.text, marca
    assert "Generar asesoría" in r.text  # sin asesoría todavía


def test_panel_muestra_asesoria_guardada(client):
    _mes(client, 7, 2)  # mes negativo
    entrada = {
        "causa_brecha": "El resultado fue -1.050.000 por 2 de 5 unidades arrendadas.",
        "recomendacion_reinversion": "Cubrir el faltante con la reserva; no reinvertir.",
        "nota_fiscal": "El mes no generó renta gravable. Estimación basada únicamente en el ingreso de este activo.",
    }
    generar_y_guardar(get_activo()["id"], 2026, 7, api_key="x", cliente=_ClienteOK(entrada))
    r = client.get("/")
    assert "2 de 5 unidades" in r.text
    assert "Generar asesoría" not in r.text
    assert "Regenerar" in r.text


def test_panel_navegacion_entre_meses(client):
    _mes(client, 6, 5)
    _mes(client, 7, 4)
    r = client.get("/")  # muestra julio (el más reciente)
    assert "Cierre Julio 2026" in r.text
    assert "← Mes anterior" in r.text
    r2 = client.get("/?anio=2026&mes=6")
    assert "Cierre Junio 2026" in r2.text
    assert "Mes siguiente →" in r2.text
