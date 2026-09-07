"""Brecha entre lo que la política de distribución ordenaba y lo que el periodo permitió.

Módulo **motor**: trabaja con números. La política reparte un resultado positivo en tres
bolsas cuyos porcentajes suman 100. Si el resultado no es positivo, ninguna bolsa se puede
financiar: la brecha es todo el faltante del periodo.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Brecha:
    resultado: float
    meta_libre: float
    meta_reinversion: float
    meta_reserva: float
    porcentaje_libre_real: float  # % del resultado que efectivamente quedó libre
    brecha_puntos: float  # porcentaje_libre_real - pct_libre  (0 o negativo)
    brecha_monto: float  # 0 si el periodo cubre la política; el faltante (negativo) si no
    en_linea: bool


def calcular_brecha(
    resultado: float,
    pct_libre: float,
    pct_reinversion: float,
    pct_reserva: float,
) -> Brecha:
    if resultado > 0:
        return Brecha(
            resultado=resultado,
            meta_libre=resultado * pct_libre / 100,
            meta_reinversion=resultado * pct_reinversion / 100,
            meta_reserva=resultado * pct_reserva / 100,
            porcentaje_libre_real=pct_libre,
            brecha_puntos=0.0,
            brecha_monto=0.0,
            en_linea=True,
        )
    return Brecha(
        resultado=resultado,
        meta_libre=0.0,
        meta_reinversion=0.0,
        meta_reserva=0.0,
        porcentaje_libre_real=0.0,
        brecha_puntos=-pct_libre,
        brecha_monto=resultado,
        en_linea=False,
    )
