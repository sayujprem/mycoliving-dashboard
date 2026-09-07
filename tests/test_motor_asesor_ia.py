"""Tarea 12: orquestación de la llamada a Anthropic."""
from pathlib import Path

from motor.asesor_ia import (
    CAMPOS_ASESORIA,
    HERRAMIENTA_ASESORIA,
    generar_asesoria,
    validar_contexto,
)

SISTEMA = "Eres un asesor. Responde solo con la herramienta."


def _contexto(**over):
    c = {
        "resultado_mes": -500_000.0,
        "moneda": "COP",
        "brecha": {"en_linea": False, "brecha_monto": -500_000.0, "porcentaje_libre_real": 0.0},
        "reserva": {"saldo": 200_000.0, "agotada": False, "meses_restantes": 0.4},
        "capex_pct_recuperado": 25.0,
        "contrato_vigencia_meses": 48,
        "notas_activo": "zonas comunes amobladas",
        "texto_fiscal": "El mes no generó renta gravable. Estimación basada únicamente en...",
    }
    c.update(over)
    return c


class _Bloque:
    type = "tool_use"
    name = "entregar_asesoria"

    def __init__(self, entrada):
        self.input = entrada


class _Respuesta:
    def __init__(self, entrada):
        self.content = [_Bloque(entrada)]


class _ClienteOK:
    ultimo_kwargs: dict = {}

    def __init__(self, entrada):
        self._entrada = entrada
        self.messages = self

    def create(self, **kwargs):
        _ClienteOK.ultimo_kwargs = kwargs
        return _Respuesta(self._entrada)


class _ClienteCaido:
    def __init__(self):
        self.messages = self

    def create(self, **kwargs):
        raise RuntimeError("boom")


def test_contexto_valido_pasa_el_esquema():
    assert validar_contexto(_contexto()) == []


def test_contexto_incompleto_se_rechaza_sin_llamar_al_api():
    ctx = _contexto()
    del ctx["texto_fiscal"]
    r = generar_asesoria(ctx, api_key="x", sistema=SISTEMA, cliente=_ClienteCaido())
    assert r.ok is False and "Contexto inválido" in r.error


def test_sin_api_key_no_llama_y_deja_pendiente():
    r = generar_asesoria(_contexto(), api_key="", sistema=SISTEMA, cliente=None)
    assert r.ok is False and "ANTHROPIC_API_KEY" in r.error


def test_llamada_ok_extrae_la_herramienta_y_fuerza_tool_choice():
    entrada = {
        "causa_brecha": "El neto fue -500.000 por 2 unidades vacías.",
        "recomendacion_reinversion": "No reinvertir; cubrir el faltante con reserva.",
        "nota_fiscal": "El mes no generó renta gravable. Estimación basada únicamente en...",
    }
    r = generar_asesoria(_contexto(), api_key="x", sistema=SISTEMA, cliente=_ClienteOK(entrada))
    assert r.ok is True and r.asesoria == entrada
    kw = _ClienteOK.ultimo_kwargs
    assert kw["tool_choice"] == {"type": "tool", "name": "entregar_asesoria"}
    assert kw["tools"][0]["name"] == "entregar_asesoria"
    assert kw["system"] == SISTEMA
    assert kw["max_tokens"] >= 1000


def test_api_caido_deja_pendiente_sin_excepcion():
    r = generar_asesoria(_contexto(), api_key="x", sistema=SISTEMA, cliente=_ClienteCaido())
    assert r.ok is False and r.error


def test_respuesta_incompleta_del_modelo_es_pendiente():
    entrada = {"causa_brecha": "x", "recomendacion_reinversion": "  ", "nota_fiscal": "y"}
    r = generar_asesoria(_contexto(), api_key="x", sistema=SISTEMA, cliente=_ClienteOK(entrada))
    assert r.ok is False and "incompleta" in r.error


def test_herramienta_pide_los_tres_campos():
    assert set(HERRAMIENTA_ASESORIA["input_schema"]["required"]) == set(CAMPOS_ASESORIA)


def test_modulo_motor_asesor_sin_vocabulario_de_dominio():
    texto = (Path(__file__).resolve().parent.parent / "motor" / "asesor_ia.py").read_text(encoding="utf-8").lower()
    for palabra in ("coliving", "inmueble", "subarriendo", "arriendo", "colombia", "canon", "art. 241"):
        assert palabra not in texto
