"""Ensambla todo lo que la vista del mes necesita en un solo diccionario.

Reúne el consolidado, el diagnóstico, la brecha, el estado de la reserva, la recuperación
del capex, los recordatorios y la asesoría guardada para un mes concreto.
"""
from __future__ import annotations

from datetime import date

from db.repositorio import (
    get_asesoria,
    get_capex,
    get_configuracion,
    get_contrato_maestro,
    get_politica,
    get_recordatorios,
    get_reportes,
    get_reserva_movimientos,
)
from dominio.capex import resumen_capex
from dominio.configuracion import horizonte_destino, horizonte_meses
from dominio.consolidado import consolidar_historico
from dominio.diagnostico import diagnostico_mes
from dominio.recordatorios import clasificar_recordatorios
from motor.politica import calcular_brecha
from motor.recordatorios import PROXIMO, VENCIDO
from motor.reserva import meses_restantes, reserva_agotada


def meses_registrados(activo_id: int) -> list[tuple[int, int]]:
    """(anio, mes) de cada mes con reporte, del más reciente al más viejo."""
    return [(r["anio"], r["mes"]) for r in get_reportes(activo_id)]


def _vigencia_restante(contrato) -> int | None:
    if not contrato or not contrato["fecha_vencimiento"]:
        return None
    v = date.fromisoformat(str(contrato["fecha_vencimiento"])[:10])
    hoy = date.today()
    return max(0, (v.year - hoy.year) * 12 + (v.month - hoy.month))


def panel_mes(activo_id: int, anio: int, mes: int) -> dict | None:
    reportes = get_reportes(activo_id)
    contrato = get_contrato_maestro(activo_id)
    politica = get_politica(activo_id)
    conf = get_configuracion(activo_id)

    consolidado = {(c.anio, c.mes): c for c in consolidar_historico(reportes, contrato)}
    if (anio, mes) not in consolidado:
        return None
    c = consolidado[(anio, mes)]
    fila_reporte = next(r for r in reportes if r["anio"] == anio and r["mes"] == mes)

    brecha = None
    if politica:
        brecha = calcular_brecha(
            c.resultado,
            politica["porcentaje_libre"],
            politica["porcentaje_reinversion"],
            politica["porcentaje_reserva"],
        )

    movimientos = {(m["anio"], m["mes"]): m for m in get_reserva_movimientos(activo_id)}
    mov = movimientos.get((anio, mes))
    saldo = float(mov["saldo_resultante"]) if mov else None
    reserva = {
        "saldo": saldo,
        "agotada": saldo is not None and reserva_agotada(saldo),
        "meses_restantes": (
            meses_restantes(saldo, -c.resultado)
            if saldo is not None and c.resultado < 0
            else None
        ),
    }

    partidas = get_capex(activo_id)
    clasificados = clasificar_recordatorios(get_recordatorios(activo_id), conf)
    recordatorios = [
        {
            "categoria": f["categoria"],
            "descripcion": f["descripcion"],
            "fecha": e.proxima_fecha,
            "dias": ("+" + str(abs(e.dias_restantes))) if e.dias_restantes < 0 else e.dias_restantes,
            "estado": "días vencido" if e.estado == VENCIDO else "días restantes",
            "tono": "rojo" if e.estado == VENCIDO else ("amarillo" if e.estado == PROXIMO else "verde"),
        }
        for f, e in clasificados
    ]

    return {
        "anio": anio,
        "mes": mes,
        "ocupacion": fila_reporte["ocupacion"],
        "consolidado": c,
        "diagnostico": diagnostico_mes(activo_id, anio, mes),
        "brecha": brecha,
        "reserva": reserva,
        "capex": resumen_capex(partidas) if partidas else None,
        "recordatorios": recordatorios,
        "recordatorios_vencidos": sum(1 for _, e in clasificados if e.estado == VENCIDO),
        "recordatorios_proximos": sum(1 for _, e in clasificados if e.estado == PROXIMO),
        "contrato": contrato,
        "contrato_vigencia_restante": _vigencia_restante(contrato),
        "horizonte_meses": horizonte_meses(conf),
        "horizonte_destino": horizonte_destino(conf),
        "asesoria": get_asesoria(activo_id, anio, mes),
    }
