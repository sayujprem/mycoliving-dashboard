"""Carga el activo del coliving y su configuración inicial COMO DATOS.

Este archivo es datos de arranque, no lógica: por eso el número de unidades, la comisión y
el rango de arriendo viven aquí y no dentro de `motor/`, `dominio/`, `db/` ni `web/`.

Idempotente: si ya existe un activo, no toca nada.
Correr:  python -m scripts.seed_coliving
"""
from datetime import date

from db.init_db import init_db
from db.repositorio import (
    crear_o_actualizar_activo,
    get_activo,
    guardar_politica,
    set_configuracion,
)

ACTIVO = {
    "nombre": "Coliving Granada",
    "tipo": "coliving",
    "unidades_totales": 5,
    "comision_administrador_pct": 10.0,
    "moneda": "COP",
    "ubicacion": "Barrio Granada, Armenia, Quindío",
    "notas": (
        "5 apartaestudios con baño privado. Zonas comunes: cocina, sala-comedor, coworking, "
        "patio de ropas, patio interior. Contratos de 6 a 12 meses, no turístico."
    ),
}

UMBRALES = {
    "ocupacion_minima_verde": "4",
    "gasto_maximo_pct_verde": "45",
    "meses_consecutivos_baja_ocupacion_para_rojo": "2",
    "arriendo_promedio_unidad": "850000",
    "ventana_aviso_recordatorio_dias": "30",
    "categorias_recordatorio": "mantenimiento, seguro, contrato",
    "horizonte_meses": "60",
    "horizonte_destino": "renta estable, sin venta prevista",
}

POLITICA = {
    "porcentaje_libre": 40,
    "porcentaje_reinversion": 40,
    "porcentaje_reserva": 20,
    "tarifa_marginal_actual": 0,
    "calcular_impuesto": 0,
}


def seed() -> None:
    init_db()
    if get_activo():
        print("Ya hay un activo configurado; no se toca nada.")
        return

    activo_id = crear_o_actualizar_activo(ACTIVO)
    for clave, valor in UMBRALES.items():
        set_configuracion(activo_id, clave, valor)
    guardar_politica(activo_id, {**POLITICA, "fecha_definicion": date.today().isoformat()})

    print(f"Activo '{ACTIVO['nombre']}' creado (id {activo_id}) con umbrales, horizonte y política inicial.")
    print("Falta el capex y los recordatorios desde /config. El contrato maestro es opcional:")
    print("si no lo defines, incluye el canon en los gastos fijos de cada informe mensual.")


if __name__ == "__main__":
    seed()
