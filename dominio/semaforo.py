"""Diagnóstico del mes: dos semáforos determinísticos y la ocupación de equilibrio.

Capa **dominio**: los criterios de "óptimo" para un coliving en subarriendo. Sin IA — el
color sale de una regla y de umbrales que el usuario define en `configuracion_dominio`. La
explicación se arma con plantillas de texto que nombran la cifra y el umbral que se cruzó.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

VERDE = "verde"
AMARILLO = "amarillo"
ROJO = "rojo"


@dataclass(frozen=True)
class Semaforo:
    estado: str
    explicacion: str


@dataclass(frozen=True)
class Diagnostico:
    resultado: Semaforo
    ocupacion: Semaforo
    ocupacion_equilibrio: int
    # True mientras no haya suficientes meses para evaluar la regla de vacancia.
    vacancia_en_espera: bool = False


def calcular_ocupacion_equilibrio(
    canon_maestro: float,
    gastos_fijos: float,
    arriendo_promedio_unidad: float,
    comision_pct: float,
) -> int:
    """Unidades que hay que tener arrendadas para no poner plata este mes."""
    neto_por_unidad = arriendo_promedio_unidad * (1 - comision_pct / 100)
    if neto_por_unidad <= 0:
        return 0
    return ceil((canon_maestro + gastos_fijos) / neto_por_unidad)


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def semaforo_resultado(
    resultado: float,
    ingreso: float,
    costos_variables: float,
    gasto_maximo_pct_verde: float,
) -> Semaforo:
    if resultado < 0:
        return Semaforo(
            ROJO,
            f"El mes cerró con un resultado negativo de {_fmt(resultado)}: el ingreso no "
            f"alcanzó a cubrir los gastos, la comisión y el canon maestro.",
        )
    pct_gasto = (costos_variables / ingreso * 100) if ingreso > 0 else 100.0
    if pct_gasto <= gasto_maximo_pct_verde:
        return Semaforo(
            VERDE,
            f"Resultado positivo de {_fmt(resultado)}. Los gastos y la comisión "
            f"consumieron {pct_gasto:.0f}% del ingreso, dentro del umbral verde de "
            f"{gasto_maximo_pct_verde:.0f}%.",
        )
    return Semaforo(
        AMARILLO,
        f"Resultado positivo de {_fmt(resultado)}, pero los gastos y la comisión "
        f"consumieron {pct_gasto:.0f}% del ingreso, por encima del umbral verde de "
        f"{gasto_maximo_pct_verde:.0f}%.",
    )


def semaforo_ocupacion(
    ocupacion: int,
    unidades_totales: int,
    ocupacion_minima_verde: int,
    ocupacion_equilibrio: int,
    meses_bajo_equilibrio: int,
    meses_para_rojo: int,
) -> Semaforo:
    if meses_para_rojo and meses_bajo_equilibrio >= meses_para_rojo:
        return Semaforo(
            ROJO,
            f"La ocupación lleva {meses_bajo_equilibrio} meses seguidos por debajo del "
            f"punto de equilibrio de {ocupacion_equilibrio}: riesgo de vacancia estructural.",
        )
    if ocupacion < ocupacion_equilibrio:
        return Semaforo(
            ROJO,
            f"Ocupación en {ocupacion} de {unidades_totales}, por debajo del punto de "
            f"equilibrio de {ocupacion_equilibrio}. A este nivel cada mes consume reserva.",
        )
    if ocupacion >= ocupacion_minima_verde:
        return Semaforo(
            VERDE,
            f"Ocupación en {ocupacion} de {unidades_totales}, en o por encima del mínimo "
            f"verde de {ocupacion_minima_verde} y del equilibrio de {ocupacion_equilibrio}.",
        )
    return Semaforo(
        AMARILLO,
        f"Ocupación en {ocupacion} de {unidades_totales}: cubre el equilibrio de "
        f"{ocupacion_equilibrio} pero está por debajo del mínimo verde de "
        f"{ocupacion_minima_verde}.",
    )
