"""Recuperación de una inversión de capital por línea recta.

Módulo **motor**: números. Una inversión se recupera de forma uniforme a lo largo de su
horizonte: a la mitad del horizonte se ha recuperado la mitad. Nunca pasa del 100 %.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecuperacionCapex:
    monto_total: float
    horizonte_meses: int
    meses_transcurridos: int
    recuperado: float
    pct_recuperado: float
    pendiente: float
    completado: bool


def recuperacion(
    monto_total: float, horizonte_meses: int, meses_transcurridos: int
) -> RecuperacionCapex:
    meses = max(0, meses_transcurridos)
    ratio = 1.0 if horizonte_meses <= 0 else min(1.0, meses / horizonte_meses)
    recuperado = monto_total * ratio
    return RecuperacionCapex(
        monto_total=monto_total,
        horizonte_meses=horizonte_meses,
        meses_transcurridos=meses,
        recuperado=recuperado,
        pct_recuperado=ratio * 100,
        pendiente=monto_total - recuperado,
        completado=ratio >= 1.0,
    )
