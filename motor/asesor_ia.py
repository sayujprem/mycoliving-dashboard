"""Orquestación de la llamada al API de Anthropic para el informe de asesoría.

Módulo **motor**: recibe un contexto y un prompt de sistema ya armados por la capa de
dominio, valida el contexto contra un esquema, llama al modelo forzando una herramienta que
devuelve un texto estructurado en tres partes, y nunca deja que un fallo del API tumbe la
aplicación: cualquier problema vuelve como `ResultadoAsesoria(ok=False, error=...)`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from config import ANTHROPIC_TIMEOUT, MODELO_ASESORIA

log = logging.getLogger(__name__)

# Sonnet 5 razona antes de responder, y esos tokens cuentan dentro de max_tokens. Con
# 4000, un razonamiento largo agotaba el cupo antes de terminar la llamada a la
# herramienta y el informe salia incompleto. 8000 deja margen; el costo maximo por
# informe sigue por debajo de 0.10 USD.
MAX_TOKENS = 8000

# El contexto llega ya calculado y la tarea es redactar un analisis corto, no resolver
# un problema abierto. "medium" rinde igual en este tipo de trabajo y razona menos, que
# es lo que se paga.
ESFUERZO = "medium"

CAMPOS_ASESORIA = ("causa_brecha", "recomendacion_reinversion", "nota_fiscal")

SCHEMA_CONTEXTO = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "resultado_mes",
        "moneda",
        "brecha",
        "reserva",
        "capex_pct_recuperado",
        "contrato_vigencia_meses",
        "notas_activo",
        "texto_fiscal",
    ],
    "properties": {
        "resultado_mes": {"type": "number"},
        "moneda": {"type": "string"},
        "brecha": {
            "type": "object",
            "additionalProperties": False,
            "required": ["en_linea", "brecha_monto", "porcentaje_libre_real"],
            "properties": {
                "en_linea": {"type": "boolean"},
                "brecha_monto": {"type": "number"},
                "porcentaje_libre_real": {"type": "number"},
                "meta_libre": {"type": "number"},
                "meta_reinversion": {"type": "number"},
                "meta_reserva": {"type": "number"},
            },
        },
        "reserva": {
            "type": "object",
            "additionalProperties": False,
            "required": ["saldo", "agotada"],
            "properties": {
                "saldo": {"type": "number"},
                "agotada": {"type": "boolean"},
                "meses_restantes": {"type": ["number", "null"]},
            },
        },
        "capex_pct_recuperado": {"type": "number"},
        "contrato_vigencia_meses": {"type": ["integer", "null"]},
        "notas_activo": {"type": "string"},
        "texto_fiscal": {"type": "string"},
    },
}

HERRAMIENTA_ASESORIA = {
    "name": "entregar_asesoria",
    "description": "Entrega el informe mensual de asesoría en tres partes concretas.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": list(CAMPOS_ASESORIA),
        "properties": {
            "causa_brecha": {
                "type": "string",
                "description": "Causa concreta de la brecha del mes, con la cifra. Una o dos frases.",
            },
            "recomendacion_reinversion": {
                "type": "string",
                "description": "Recomendación concreta sobre el excedente o el faltante del mes.",
            },
            "nota_fiscal": {
                "type": "string",
                "description": "La nota fiscal en prosa, integrando el texto_fiscal recibido "
                "sin contradecirlo y conservando su advertencia de alcance.",
            },
        },
    },
}

_VALIDADOR = Draft202012Validator(SCHEMA_CONTEXTO)


@dataclass(frozen=True)
class ResultadoAsesoria:
    ok: bool
    asesoria: dict | None = None
    error: str | None = None


def validar_contexto(contexto: dict) -> list[str]:
    return [e.message for e in _VALIDADOR.iter_errors(contexto)]


def _prompt_usuario(c: dict) -> str:
    b = c["brecha"]
    r = c["reserva"]
    return (
        f"Moneda: {c['moneda']}.\n"
        f"Resultado del mes: {c['resultado_mes']:,.0f}.\n"
        f"Brecha vs. política: {'en línea' if b['en_linea'] else 'no cubre la política'}; "
        f"faltante {b['brecha_monto']:,.0f}; porcentaje libre real {b['porcentaje_libre_real']:g}%.\n"
        f"Fondo de reserva: saldo {r['saldo']:,.0f}; "
        f"{'agotado' if r['agotada'] else 'con saldo'}; "
        f"meses restantes {r.get('meses_restantes')}.\n"
        f"Recuperación de capex: {c['capex_pct_recuperado']:.0f}%.\n"
        f"Vigencia restante del contrato maestro (meses): {c['contrato_vigencia_meses']}.\n"
        f"Notas del activo: {c['notas_activo'] or '—'}.\n"
        f"Nota fiscal ya calculada (intégrala sin contradecirla):\n{c['texto_fiscal']}"
    )


def _mensaje_error(exc: Exception) -> str:
    """Traduce el fallo a un mensaje fijo para el usuario.

    El detalle crudo del proveedor va al log, nunca a la pantalla: puede incluir
    identificadores de la cuenta de Anthropic, y al usuario final no le sirve.
    """
    log.warning("Fallo del API de Anthropic: %r", exc)
    try:
        import anthropic

        if isinstance(exc, anthropic.AuthenticationError):
            return "El servicio de asesoría no está disponible. Avisa al administrador."
        if isinstance(exc, anthropic.RateLimitError):
            return "El servicio de asesoría está saturado. Intenta en unos minutos."
        if isinstance(exc, anthropic.APITimeoutError):
            return "El informe tardó demasiado en generarse. Intenta de nuevo."
        if isinstance(exc, anthropic.APIConnectionError):
            return "No se pudo conectar con el servicio de asesoría. Intenta de nuevo."
        if isinstance(exc, anthropic.APIStatusError):
            detalle = (getattr(exc, "message", "") or str(exc)).lower()
            if "credit" in detalle or "spend" in detalle or "limit" in detalle:
                # Se agoto el credito o se toco el tope de gasto de la consola.
                return "Se alcanzó el tope mensual de asesorías. Vuelve a intentar el próximo mes."
            return "El servicio de asesoría devolvió un error. Intenta de nuevo más tarde."
    except Exception:  # noqa: BLE001
        pass
    return "No se pudo generar la asesoría. Intenta de nuevo más tarde."


def generar_asesoria(
    contexto: dict, *, api_key: str, sistema: str, workspace_id: str = "", cliente=None
) -> ResultadoAsesoria:
    errores = validar_contexto(contexto)
    if errores:
        return ResultadoAsesoria(ok=False, error="Contexto inválido: " + "; ".join(errores))
    if not api_key and cliente is None:
        return ResultadoAsesoria(ok=False, error="No hay ANTHROPIC_API_KEY configurada.")

    try:
        if cliente is None:
            import anthropic

            headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
            cliente = anthropic.Anthropic(
                api_key=api_key,
                default_headers=headers,
                # La funcion en Vercel tiene su propio limite de duracion (vercel.json).
                # Sin reintentos automaticos, el peor caso es un solo timeout y queda
                # por debajo de ese limite; el usuario puede volver a pulsar.
                timeout=ANTHROPIC_TIMEOUT,
                max_retries=0,
            )
        respuesta = cliente.messages.create(
            model=MODELO_ASESORIA,
            max_tokens=MAX_TOKENS,
            output_config={"effort": ESFUERZO},
            system=sistema,
            tools=[HERRAMIENTA_ASESORIA],
            tool_choice={"type": "tool", "name": "entregar_asesoria"},
            messages=[{"role": "user", "content": _prompt_usuario(contexto)}],
        )
    except Exception as exc:  # noqa: BLE001 - un fallo del API deja la asesoría pendiente
        return ResultadoAsesoria(ok=False, error=_mensaje_error(exc))

    parada = getattr(respuesta, "stop_reason", None)
    if parada == "refusal":
        return ResultadoAsesoria(ok=False, error="El modelo no pudo generar este informe. Revisa las notas del activo.")
    if parada == "max_tokens":
        log.warning("Asesoría cortada por max_tokens (%s)", MAX_TOKENS)
        return ResultadoAsesoria(ok=False, error="El informe quedó incompleto. Intenta de nuevo.")

    for bloque in getattr(respuesta, "content", []):
        if getattr(bloque, "type", None) == "tool_use" and getattr(bloque, "name", None) == "entregar_asesoria":
            entrada = dict(bloque.input)
            if any(not str(entrada.get(k, "")).strip() for k in CAMPOS_ASESORIA):
                return ResultadoAsesoria(ok=False, error="La respuesta del modelo vino incompleta.")
            return ResultadoAsesoria(ok=True, asesoria=entrada)
    return ResultadoAsesoria(ok=False, error="El modelo no llamó a la herramienta esperada.")
