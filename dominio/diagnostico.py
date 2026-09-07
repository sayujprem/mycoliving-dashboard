"""Arma el diagnóstico del mes: junta el informe, el contrato, los umbrales y el histórico
y produce los dos semáforos con su explicación.
"""
from __future__ import annotations

from db.repositorio import (
    get_activo,
    get_configuracion,
    get_contrato_maestro,
    get_reportes,
)
from dominio.configuracion import leer_entero, leer_numero
from dominio.consolidado import consolidar_historico
from dominio.semaforo import (
    Diagnostico,
    calcular_ocupacion_equilibrio,
    semaforo_ocupacion,
    semaforo_resultado,
)


def contar_meses_bajo_equilibrio(
    reportes_desc, canon: float, arriendo_promedio: float, comision_pct: float
) -> int:
    """`reportes_desc`: el mes en cuestión primero, luego los anteriores."""
    racha = 0
    for r in reportes_desc:
        eq = calcular_ocupacion_equilibrio(canon, r["gastos_fijos"], arriendo_promedio, comision_pct)
        if eq > 0 and r["ocupacion"] < eq:
            racha += 1
        else:
            break
    return racha


def diagnostico_mes(activo_id: int, anio: int, mes: int) -> Diagnostico | None:
    activo = get_activo()
    if not activo:
        return None
    conf = get_configuracion(activo_id)
    contrato = get_contrato_maestro(activo_id)
    canon = float(contrato["canon_mensual"]) if contrato else 0.0
    comision_pct = activo["comision_administrador_pct"]
    arriendo_promedio = leer_numero(conf, "arriendo_promedio_unidad")
    minimo_verde = leer_entero(conf, "ocupacion_minima_verde")
    gasto_maximo = leer_numero(conf, "gasto_maximo_pct_verde", 100.0)
    meses_para_rojo = leer_entero(conf, "meses_consecutivos_baja_ocupacion_para_rojo")

    reportes = get_reportes(activo_id)  # descendente
    consolidado = {(c.anio, c.mes): c for c in consolidar_historico(reportes, contrato)}
    idx = next(
        (i for i, r in enumerate(reportes) if r["anio"] == anio and r["mes"] == mes), None
    )
    if idx is None:
        return None

    r = reportes[idx]
    c = consolidado[(anio, mes)]
    equilibrio = calcular_ocupacion_equilibrio(
        canon, r["gastos_fijos"], arriendo_promedio, comision_pct
    )
    racha = contar_meses_bajo_equilibrio(
        reportes[idx:], canon, arriendo_promedio, comision_pct
    )
    # meses de historia hasta este mes, inclusive
    meses_con_historia = len(reportes) - idx
    en_espera = meses_para_rojo > 1 and meses_con_historia < meses_para_rojo

    return Diagnostico(
        resultado=semaforo_resultado(c.resultado, c.ingreso, c.costos_variables, gasto_maximo),
        ocupacion=semaforo_ocupacion(
            r["ocupacion"],
            activo["unidades_totales"],
            minimo_verde,
            equilibrio,
            racha,
            meses_para_rojo,
        ),
        ocupacion_equilibrio=equilibrio,
        vacancia_en_espera=en_espera,
    )
