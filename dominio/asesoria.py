"""Genera el informe mensual de asesoría (Paso 5) y lo guarda.

Arma el contexto desde el histórico, el diagnóstico, la brecha, la reserva, el capex y la
nota fiscal; se lo pasa al motor para la llamada al modelo; y persiste el resultado en
`asesoria_generada`. Si el modelo no está disponible, no guarda nada y devuelve el error
para que la vista ofrezca reintentar.
"""
from __future__ import annotations

from datetime import date

from config import ANTHROPIC_API_KEY, ANTHROPIC_WORKSPACE_ID
from db.repositorio import (
    get_activo_por_id,
    get_capex,
    get_configuracion,
    get_contrato_maestro,
    get_politica,
    get_reportes,
    get_reserva_movimientos,
    guardar_asesoria,
)
from dominio.capex import resumen_capex
from dominio.configuracion import horizonte_meses
from dominio.consolidado import consolidar_historico
from dominio.diagnostico import diagnostico_mes
from dominio.fiscal import texto_fiscal
from motor.asesor_ia import ResultadoAsesoria, generar_asesoria
from motor.politica import calcular_brecha
from motor.reserva import meses_restantes, reserva_agotada

SISTEMA_ASESORIA = (
    "Eres el asesor financiero y fiscal de una operación de subarriendo de vivienda "
    "(rent-to-rent) en Colombia. Escribe en español, directo y concreto. Cada frase debe "
    "nombrar una cifra o una causa puntual del mes; nunca des consejos genéricos. La nota "
    "fiscal debe integrar el texto_fiscal recibido sin contradecirlo y conservar su "
    "advertencia de alcance. Responde solo llamando a la herramienta entregar_asesoria."
)


def _meses_hasta(fecha_iso) -> int:
    v = date.fromisoformat(str(fecha_iso)[:10])
    hoy = date.today()
    return max(0, (v.year - hoy.year) * 12 + (v.month - hoy.month))


def armar_contexto(activo_id: int, anio: int, mes: int) -> dict | None:
    activo = get_activo_por_id(activo_id)
    if not activo:
        return None

    reportes = get_reportes(activo_id)
    contrato = get_contrato_maestro(activo_id)
    politica = get_politica(activo_id)
    consolidado = {(c.anio, c.mes): c for c in consolidar_historico(reportes, contrato)}
    if (anio, mes) not in consolidado:
        return None
    c = consolidado[(anio, mes)]

    if politica:
        b = calcular_brecha(
            c.resultado,
            politica["porcentaje_libre"],
            politica["porcentaje_reinversion"],
            politica["porcentaje_reserva"],
        )
        brecha = {
            "en_linea": b.en_linea,
            "brecha_monto": b.brecha_monto,
            "porcentaje_libre_real": b.porcentaje_libre_real,
            "meta_libre": b.meta_libre,
            "meta_reinversion": b.meta_reinversion,
            "meta_reserva": b.meta_reserva,
        }
    else:
        brecha = {"en_linea": True, "brecha_monto": 0.0, "porcentaje_libre_real": 0.0}

    movimientos = {(m["anio"], m["mes"]): m for m in get_reserva_movimientos(activo_id)}
    mov = movimientos.get((anio, mes))
    saldo = float(mov["saldo_resultante"]) if mov else 0.0
    reserva = {
        "saldo": saldo,
        "agotada": bool(mov) and reserva_agotada(saldo),
        "meses_restantes": meses_restantes(saldo, -c.resultado) if c.resultado < 0 else None,
    }

    partidas = get_capex(activo_id)
    capex_pct = resumen_capex(partidas).pct_recuperado if partidas else 0.0

    conf = get_configuracion(activo_id)
    vigencia_restante = (
        _meses_hasta(contrato["fecha_vencimiento"])
        if contrato and contrato["fecha_vencimiento"]
        else horizonte_meses(conf)
    )

    calcula = bool(politica["calcular_impuesto"]) if politica else False
    tarifa = politica["tarifa_marginal_actual"] if politica else 0.0

    return {
        "resultado_mes": float(c.resultado),
        "moneda": activo["moneda"],
        "brecha": brecha,
        "reserva": reserva,
        "capex_pct_recuperado": float(capex_pct),
        "contrato_vigencia_meses": vigencia_restante,
        "notas_activo": activo["notas"] or "",
        "texto_fiscal": texto_fiscal(c.resultado, tarifa, calcula),
    }


def generar_y_guardar(
    activo_id: int, anio: int, mes: int, *, api_key: str | None = None, cliente=None
) -> ResultadoAsesoria:
    contexto = armar_contexto(activo_id, anio, mes)
    if contexto is None:
        return ResultadoAsesoria(ok=False, error="No hay datos suficientes para ese mes.")

    resultado = generar_asesoria(
        contexto,
        api_key=api_key if api_key is not None else ANTHROPIC_API_KEY,
        sistema=SISTEMA_ASESORIA,
        workspace_id=ANTHROPIC_WORKSPACE_ID,
        cliente=cliente,
    )
    if not resultado.ok:
        return resultado

    a = resultado.asesoria
    diag = diagnostico_mes(activo_id, anio, mes)
    guardar_asesoria(
        activo_id,
        {
            "anio": anio,
            "mes": mes,
            "semaforo_resultado": diag.resultado.estado if diag else None,
            "semaforo_ocupacion": diag.ocupacion.estado if diag else None,
            "resultado_mes": contexto["resultado_mes"],
            "ocupacion_equilibrio": diag.ocupacion_equilibrio if diag else None,
            "porcentaje_libre_real": contexto["brecha"]["porcentaje_libre_real"],
            "brecha_frente_a_meta": contexto["brecha"]["brecha_monto"],
            "capex_recuperado_pct": contexto["capex_pct_recuperado"],
            "texto_asesoria": (
                f"Causa de la brecha: {a['causa_brecha']}\n\n"
                f"Recomendación: {a['recomendacion_reinversion']}"
            ),
            "texto_fiscal": a["nota_fiscal"],
            "fecha_generacion": date.today().isoformat(),
        },
    )
    return resultado
