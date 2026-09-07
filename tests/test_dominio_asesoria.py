"""Tarea 13: generación y guardado del informe mensual de asesoría."""
import os
import re

import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_asesoria
from dominio.asesoria import SISTEMA_ASESORIA, armar_contexto, generar_y_guardar
from main import app
from motor.asesor_ia import validar_contexto


class _Bloque:
    type = "tool_use"
    name = "entregar_asesoria"

    def __init__(self, entrada):
        self.input = entrada


class _Respuesta:
    def __init__(self, entrada):
        self.content = [_Bloque(entrada)]


class _ClienteOK:
    def __init__(self, entrada):
        self._entrada = entrada
        self.messages = self

    def create(self, **kwargs):
        return _Respuesta(self._entrada)


@pytest.fixture
def client():
    drop_all()
    init_db()
    c = TestClient(app)
    c.post(
        "/config/activo",
        data={"nombre": "Coliving Granada", "tipo": "coliving", "unidades_totales": "5",
              "comision_administrador_pct": "10", "moneda": "COP", "notas": "zonas comunes amobladas"},
        follow_redirects=False,
    )
    c.post(
        "/config/contrato",
        data={"canon_mensual": "3000000", "fecha_inicio": "2026-01-01",
              "fecha_vencimiento": "2031-01-01", "vigencia_meses": "60", "ventana_preaviso_dias": "90"},
        follow_redirects=False,
    )
    c.post(
        "/config/politica",
        data={"porcentaje_libre": "40", "porcentaje_reinversion": "40", "porcentaje_reserva": "20",
              "calcular_impuesto": "1", "tarifa_marginal_actual": "19"},
        follow_redirects=False,
    )
    c.post(
        "/config/umbrales",
        data={"ocupacion_minima_verde": "4", "gasto_maximo_pct_verde": "50",
              "meses_consecutivos_baja_ocupacion_para_rojo": "2",
              "arriendo_promedio_unidad": "900000", "ventana_aviso_recordatorio_dias": "30"},
        follow_redirects=False,
    )
    data = {"mes": "7", "anio": "2026", "gastos_fijos": "300000", "gastos_variables": "100000",
            "comision_admin": "450000", "novedades": ""}
    for i in (1, 2):
        data[f"unidad_{i}_arrendada"] = "1"
        data[f"unidad_{i}_ingreso"] = "900000"
    c.post("/registro", data=data, follow_redirects=False)
    return c


def test_armar_contexto_produce_un_payload_valido(client):
    ctx = armar_contexto(get_activo()["id"], 2026, 7)
    assert ctx is not None
    assert validar_contexto(ctx) == []
    assert ctx["resultado_mes"] < 0  # 2 de 5 unidades con canon de 3M
    assert "advertencia" not in ctx["texto_fiscal"].lower() or "Estimación" in ctx["texto_fiscal"]


def test_sistema_menciona_cifras_y_advertencia():
    assert "cifra" in SISTEMA_ASESORIA
    assert "advertencia de alcance" in SISTEMA_ASESORIA


def test_generar_y_guardar_persiste_con_cliente_falso(client):
    entrada = {
        "causa_brecha": "El resultado del mes fue -1.050.000 porque solo 2 de 5 unidades estaban arrendadas.",
        "recomendacion_reinversion": "No reinvertir este mes; cubrir el faltante de 1.050.000 con la reserva.",
        "nota_fiscal": "El mes no generó renta gravable por este activo. Estimación basada únicamente en el ingreso de este activo.",
    }
    r = generar_y_guardar(get_activo()["id"], 2026, 7, api_key="x", cliente=_ClienteOK(entrada))
    assert r.ok is True
    fila = get_asesoria(get_activo()["id"], 2026, 7)
    assert fila is not None
    assert "2 de 5 unidades" in fila["texto_asesoria"]
    assert "reserva" in fila["texto_asesoria"].lower()
    assert fila["semaforo_resultado"] == "rojo"
    assert fila["texto_fiscal"].startswith("El mes no generó renta gravable")


def test_ruta_post_sin_api_key_muestra_error_y_no_guarda(client):
    r = client.post("/asesoria/2026/7", follow_redirects=False)
    assert r.status_code == 303
    assert "/historico?error_asesoria=" in r.headers["location"]
    assert get_asesoria(get_activo()["id"], 2026, 7) is None
    pagina = client.get("/historico" + r.headers["location"].split("/historico", 1)[1])
    assert "No se pudo generar la asesoría" in pagina.text


def test_historico_ofrece_generar_cuando_no_hay_asesoria(client):
    r = client.get("/historico")
    assert 'action="/asesoria/2026/7"' in r.text
    assert "Generar" in r.text


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requiere ANTHROPIC_API_KEY para una corrida real",
)
def test_corrida_real_nombra_una_cifra(client):
    r = generar_y_guardar(get_activo()["id"], 2026, 7)
    assert r.ok is True, r.error
    fila = get_asesoria(get_activo()["id"], 2026, 7)
    assert re.search(r"\d", fila["texto_asesoria"])  # nombra alguna cifra
    assert len(fila["texto_asesoria"]) > 60  # no es una línea genérica
