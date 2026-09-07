"""Resultado de un periodo y consolidación del histórico.

Módulo **motor**: no sabe qué tipo de activo es ni en qué país opera. Trabaja con números.
El resultado de un periodo es el ingreso menos los costos variables del periodo (gastos más
comisión del administrador) menos la obligación fija que se debe cada periodo.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoPeriodo:
    anio: int
    mes: int
    ingreso: float
    costos_variables: float  # gastos del periodo + comisión del administrador
    obligacion_fija: float  # pago fijo que se debe cada periodo
    resultado: float  # ingreso - costos_variables - obligacion_fija


def calcular_resultado(
    ingreso: float,
    comision: float,
    gastos_fijos: float,
    gastos_variables: float,
    obligacion_fija: float,
) -> float:
    return ingreso - comision - (gastos_fijos + gastos_variables) - obligacion_fija


def consolidar(periodos: Iterable[Mapping], obligacion_fija: float) -> list[ResultadoPeriodo]:
    """`periodos`: cada uno con las claves anio, mes, ingreso, comision, gastos_fijos,
    gastos_variables. Devuelve una fila por periodo, en el mismo orden de entrada."""
    filas: list[ResultadoPeriodo] = []
    for p in periodos:
        variables = p["comision"] + p["gastos_fijos"] + p["gastos_variables"]
        filas.append(
            ResultadoPeriodo(
                anio=p["anio"],
                mes=p["mes"],
                ingreso=p["ingreso"],
                costos_variables=variables,
                obligacion_fija=obligacion_fija,
                resultado=p["ingreso"] - variables - obligacion_fija,
            )
        )
    return filas
