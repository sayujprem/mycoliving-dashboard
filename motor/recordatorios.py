"""Cálculo de la próxima fecha de un recordatorio y su clasificación.

Módulo **motor**: fechas y números. Un recordatorio es periódico (última fecha más una
frecuencia en meses) o tiene una fecha de vencimiento fija. Según los días que falten y una
ventana de aviso configurable, queda en uno de tres estados: vencido, próximo o al día.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

VENCIDO = "vencido"
PROXIMO = "proximo"
AL_DIA = "al_dia"


@dataclass(frozen=True)
class EstadoRecordatorio:
    proxima_fecha: date
    dias_restantes: int  # negativo si ya venció
    estado: str


def sumar_meses(base: date, meses: int) -> date:
    total = base.month - 1 + meses
    anio = base.year + total // 12
    mes = total % 12 + 1
    dia = min(base.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def proxima_fecha(
    ultima_fecha: date | None,
    frecuencia_meses: int | None,
    fecha_vencimiento_fija: date | None,
) -> date:
    if frecuencia_meses and ultima_fecha:
        return sumar_meses(ultima_fecha, frecuencia_meses)
    if fecha_vencimiento_fija:
        return fecha_vencimiento_fija
    raise ValueError(
        "El recordatorio necesita una frecuencia con última fecha, o una fecha fija."
    )


def clasificar(prox: date, hoy: date, ventana_dias: int) -> EstadoRecordatorio:
    dias = (prox - hoy).days
    if dias < 0:
        estado = VENCIDO
    elif dias <= ventana_dias:
        estado = PROXIMO
    else:
        estado = AL_DIA
    return EstadoRecordatorio(proxima_fecha=prox, dias_restantes=dias, estado=estado)
