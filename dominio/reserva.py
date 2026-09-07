"""Recálculo del fondo de reserva sobre todo el histórico del activo.

`reserva_movimiento` es una tabla derivada: se reconstruye entera cada vez que cambia algo
que afecte el resultado de los periodos (un mes nuevo o corregido, la política, o el canon
del contrato maestro).
"""
from db.repositorio import (
    get_contrato_maestro,
    get_politica,
    get_reportes,
    reemplazar_reserva_movimientos,
)
from motor.reserva import trayectoria
from motor.resultado import calcular_resultado


def recalcular_reserva(activo_id: int) -> None:
    politica = get_politica(activo_id)
    if not politica:
        reemplazar_reserva_movimientos(activo_id, [])
        return

    contrato = get_contrato_maestro(activo_id)
    canon = float(contrato["canon_mensual"]) if contrato else 0.0
    pct_reserva = politica["porcentaje_reserva"]

    # get_reportes viene descendente; la trayectoria necesita orden cronológico ascendente.
    reportes = list(reversed(get_reportes(activo_id)))
    periodos = [
        (
            r["anio"],
            r["mes"],
            calcular_resultado(
                r["ingreso_subarriendo"],
                r["comision_admin"],
                r["gastos_fijos"],
                r["gastos_variables"],
                canon,
            ),
        )
        for r in reportes
    ]
    movimientos = trayectoria(periodos, pct_reserva)
    reemplazar_reserva_movimientos(
        activo_id,
        [
            {
                "anio": m.anio,
                "mes": m.mes,
                "monto": m.monto,
                "saldo_resultante": m.saldo_resultante,
            }
            for m in movimientos
        ],
    )
