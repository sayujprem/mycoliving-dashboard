"""Traducción entre el informe de la inmobiliaria y el motor de consolidación.

El informe trae `ingreso_subarriendo`, `comision_admin`, `gastos_fijos` y `gastos_variables`.
La obligación fija del periodo es el canon del contrato maestro. Este archivo hace el mapeo;
el cálculo vive en `motor.resultado`.
"""
from motor.resultado import ResultadoPeriodo, consolidar


def consolidar_historico(reportes, contrato_maestro) -> list[ResultadoPeriodo]:
    canon = float(contrato_maestro["canon_mensual"]) if contrato_maestro else 0.0
    periodos = [
        {
            "anio": r["anio"],
            "mes": r["mes"],
            "ingreso": r["ingreso_subarriendo"],
            "comision": r["comision_admin"],
            "gastos_fijos": r["gastos_fijos"],
            "gastos_variables": r["gastos_variables"],
        }
        for r in reportes
    ]
    return consolidar(periodos, canon)
