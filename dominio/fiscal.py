"""Conocimiento fiscal colombiano. Único archivo con lógica tributaria del proyecto.

Si cambia una ley, o si el sistema se aplica en otro país, se toca solo este archivo.

Marco: el ingreso por subarriendo es renta no laboral dentro de la cédula general (Estatuto
Tributario, leyes 2010 de 2019 y 2277 de 2022). El canon que se paga a la propietaria y los
gastos asociados son costos deducibles de ese ingreso. La tarifa es progresiva por tramos
(art. 241): 0 %, 19 %, 28 %, 33 %, 35 %, 37 % y 39 %. El tramo marginal lo fija la renta
gravable total del año, no este activo aislado.
"""
from __future__ import annotations

# Tramos del art. 241 ET, en UVT. (desde, hasta_o_None, tarifa_marginal_pct)
TABLA_ART_241 = [
    (0, 1090, 0),
    (1090, 1700, 19),
    (1700, 4100, 28),
    (4100, 8670, 33),
    (8670, 18970, 35),
    (18970, 31000, 37),
    (31000, None, 39),
]

ADVERTENCIA_ALCANCE = (
    "Estimación basada únicamente en el ingreso de este activo, no en tu situación fiscal "
    "total. No cubre el periodo de remodelación."
)


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def resumen_tabla_241() -> str:
    tramos = ", ".join(str(t[2]) + " %" for t in TABLA_ART_241)
    return f"Tarifas de la cédula general (art. 241 ET): {tramos}."


def texto_fiscal(
    resultado_mes: float,
    tarifa_marginal_pct: float,
    calcular_impuesto: bool,
) -> str:
    """Nota fiscal determinística del mes. El Paso 5 la integra en prosa con IA."""
    if not calcular_impuesto:
        cuerpo = (
            "No se calcula impuesto. El resultado neto de este activo se suma a tu renta "
            "del año en la cédula general (renta no laboral); confirma con tu contador la "
            "tarifa marginal que te corresponde."
        )
    elif resultado_mes > 0:
        impuesto = resultado_mes * tarifa_marginal_pct / 100
        cuerpo = (
            f"Con una tarifa marginal del {tarifa_marginal_pct:g} %, el impuesto estimado "
            f"sobre el resultado del mes ({_fmt(resultado_mes)}) es {_fmt(impuesto)}. El "
            f"canon que pagas a la propietaria y los gastos asociados ya están descontados "
            f"de esa base y son deducibles del ingreso por subarriendo."
        )
    else:
        cuerpo = (
            "El mes no generó renta gravable por este activo. Una pérdida del periodo tiene "
            "compensación limitada dentro de la cédula general; consúltalo con tu contador."
        )
    return f"{cuerpo} {ADVERTENCIA_ALCANCE}"
