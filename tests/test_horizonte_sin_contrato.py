"""La plataforma funciona completa sin contrato maestro, con horizonte ajustable."""
import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_asesoria, get_contrato_maestro
from dominio.asesoria import armar_contexto, generar_y_guardar
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
    c.post("/config/politica", data={"porcentaje_libre": "40", "porcentaje_reinversion": "40",
           "porcentaje_reserva": "20"}, follow_redirects=False)
    c.post("/config/umbrales", data={
        "ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "45",
        "meses_consecutivos_baja_ocupacion_para_rojo": "2", "arriendo_promedio_unidad": "850000",
        "ventana_aviso_recordatorio_dias": "30",
        "horizonte_meses": "36", "horizonte_destino": "vender en 3 años",
    }, follow_redirects=False)
    c.post("/config/capex", data={"concepto": "Amoblado zonas comunes", "monto": "9000000",
           "fecha": "2026-06-01", "horizonte_meses": "36"}, follow_redirects=False)
    c.post("/config/recordatorios", data={"categoria": "seguro", "descripcion": "Póliza",
           "fecha_vencimiento_fija": "2026-12-01"}, follow_redirects=False)
    return c


def _mes(client, mes, arrendadas):
    data = {"mes": str(mes), "anio": "2026", "gastos_fijos": "3300000",  # incluye canon
            "gastos_variables": "150000", "comision_admin": "450000", "novedades": ""}
    for i in range(1, arrendadas + 1):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    return client.post("/registro", data=data, follow_redirects=False)


def test_nunca_se_configuro_contrato_maestro(client):
    assert get_contrato_maestro(get_activo()["id"]) is None


def test_capex_sugiere_el_horizonte_configurado_sin_contrato(client):
    r = client.get("/config/capex")
    assert 'value="36"' in r.text


def test_registro_y_panel_funcionan_sin_contrato(client):
    r = _mes(client, 7, 4)
    assert r.status_code == 303
    activo = get_activo()
    datos = panel_mes(activo["id"], 2026, 7)
    # resultado = ingreso - comision - gastos, sin descontar canon aparte (va en gastos_fijos)
    ingreso = 4 * 900_000
    esperado = ingreso - 450_000 - (3_300_000 + 150_000)
    assert datos["consolidado"].resultado == pytest.approx(esperado)
    assert datos["consolidado"].obligacion_fija == 0.0
    assert datos["horizonte_meses"] == 36
    assert datos["horizonte_destino"] == "vender en 3 años"

    html = client.get("/").text
    assert "HORIZONTE" in html
    assert "36 meses" in html
    assert "vender en 3 años" in html
    assert "Contrato maestro" not in html  # no se muestra el bloque opcional si no está definido


def test_config_marca_el_contrato_como_opcional(client):
    html = client.get("/config").text
    assert "Contrato maestro (opcional)" in html
    assert "No es necesario para operar" in html


def test_asesoria_usa_el_horizonte_configurado_como_ventana(client):
    _mes(client, 7, 4)
    ctx = armar_contexto(get_activo()["id"], 2026, 7)
    assert ctx["contrato_vigencia_meses"] == 36


def test_flujo_completo_de_asesoria_sin_contrato_maestro(client):
    _mes(client, 7, 2)  # mes flojo
    entrada = {
        "causa_brecha": "El resultado del mes fue negativo por baja ocupación (2 de 5 unidades).",
        "recomendacion_reinversion": "No reinvertir; cubrir el faltante con la reserva acumulada.",
        "nota_fiscal": "El mes no generó renta gravable. Estimación basada únicamente en el ingreso de este activo.",
    }
    resultado = generar_y_guardar(get_activo()["id"], 2026, 7, api_key="x", cliente=_ClienteOK(entrada))
    assert resultado.ok is True
    assert get_asesoria(get_activo()["id"], 2026, 7) is not None
    html = client.get("/").text
    assert "2 de 5 unidades" in html
