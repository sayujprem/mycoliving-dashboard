"""Trayectoria del fondo de reserva a lo largo del histórico.

Módulo **motor**: trabaja con números. Cada periodo mueve el fondo: si el resultado es
positivo, entra la fracción que la política destina a reserva; si es negativo, sale todo el
faltante. El saldo es acumulativo.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class MovimientoReserva:
    anio: int
    mes: int
    monto: float  # entra (+) o sale (−) del fondo este periodo
    saldo_resultante: float


def trayectoria(
    periodos: Iterable[tuple[int, int, float]],
    pct_reserva: float,
    saldo_inicial: float = 0.0,
) -> list[MovimientoReserva]:
    """`periodos`: iterable de (anio, mes, resultado), en orden cronológico ascendente."""
    saldo = saldo_inicial
    movimientos: list[MovimientoReserva] = []
    for anio, mes, resultado in periodos:
        monto = resultado * pct_reserva / 100 if resultado > 0 else resultado
        saldo += monto
        movimientos.append(MovimientoReserva(anio, mes, monto, saldo))
    return movimientos


def meses_restantes(saldo_actual: float, deficit_mensual_esperado: float) -> float | None:
    """None si no hay déficit (la reserva no se está consumiendo)."""
    if deficit_mensual_esperado <= 0:
        return None
    return max(saldo_actual, 0.0) / deficit_mensual_esperado


def reserva_agotada(saldo_actual: float) -> bool:
    return saldo_actual <= 0
