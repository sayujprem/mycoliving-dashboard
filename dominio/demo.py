"""Datos de ejemplo para ver el dashboard entero funcionando antes de cargar cifras reales.

Seis meses que recorren los tres colores en ambos semáforos, dos partidas de capex y tres
recordatorios (uno vencido, uno próximo, uno al día). Se marcan como demo y se pueden quitar
de un golpe sin tocar nada real.

**Por qué las cifras viven aquí y no en `scripts/`**: las de `scripts/seed_coliving.py` son
la operación real del usuario y tienen que ser editables sin tocar código. Estas son fixture
de una funcionalidad — el criterio de aceptación de "el dashboard se ve completo" — y `web/`
las necesita para el botón de limpiar, así que no pueden vivir en `scripts/`.

**Cómo se marca el estado**: dos claves en `configuracion_dominio`, sin tabla ni columna
nueva. Es estado operativo en una tabla que por lo demás guarda umbrales de dominio; la
alternativa limpia sería una tabla `estado_app`, pero no justifica un cambio de esquema para
dos claves. Como `/config` y `/config/umbrales` iteran sobre `CLAVES_CONFIGURACION`, estas
claves son invisibles en la interfaz y el formulario nunca las pisa.
"""
from __future__ import annotations

from datetime import date, timedelta

from db.repositorio import (
    agregar_capex,
    agregar_recordatorio,
    borrar_configuracion,
    eliminar_asesoria,
    eliminar_capex,
    eliminar_recordatorio,
    eliminar_reporte,
    get_activo,
    get_capex,
    get_configuracion,
    get_recordatorios,
    get_reportes,
    guardar_reporte,
    set_configuracion,
)
from dominio.recordatorios import calcular_proxima_fecha
from dominio.reserva import recalcular_reserva

CLAVE_MARCA = "demo_cargado"
CLAVE_MESES = "demo_meses"

# Todo lo que carga la demo lleva este prefijo, para poder quitarlo sin tocar lo real.
PREFIJO = "Demo · "

# Los umbrales contra los que están calibradas las cifras de abajo. Si el usuario los
# cambió, los colores pueden variar; `cargar_demo` lo avisa en vez de fallar.
UMBRALES_ASUMIDOS = {
    "ocupacion_minima_verde": 4,
    "gasto_maximo_pct_verde": 80,
    "meses_consecutivos_baja_ocupacion_para_rojo": 2,
    "arriendo_promedio_unidad": 850_000,
}

# Tiene que coincidir con `arriendo_promedio_unidad` del seed: de ahí sale la ocupación de
# equilibrio, y si no coinciden el mes amarillo se cae a rojo.
ARRIENDO_UNIDAD = 850_000

# (unidades arrendadas, gastos fijos, gastos variables, novedades).
# El canon de la propietaria va dentro de gastos_fijos: esta operación no usa contrato
# maestro. La ocupación de equilibrio sale de gastos_fijos / (arriendo × 0,9).
#
# Neto por unidad = 850.000 × 0,9 = 765.000. Equilibrio = ceil(gastos_fijos / 765.000).
#
#  #  ocu   resultado   %gasto  semáforo resultado  equil.  semáforo ocupación     saldo
#  1   5      +925.000   78,2%       verde            4          verde            185.000
#  2   5      +875.000   79,4%       verde            4          verde            360.000
#  3   3       +15.000   99,4%     amarillo           3        amarillo           363.000
#  4   5      +925.000   78,2%       verde            4          verde            548.000
#  5   2    −1.470.000      —         rojo            4           rojo           −922.000
#  6   2    −1.420.000      —         rojo            4     rojo (vacancia)     −2.342.000
#
# El mes 3 es la pieza delicada: el amarillo de ocupación solo existe cuando
# equilibrio ≤ ocupación < ocupacion_minima_verde, y eso obliga a bajar los gastos fijos
# a 2.200.000 para que el equilibrio caiga a 3.
MESES_DEMO = [
    (5, 2_800_000, 100_000, "Casa llena. Se renovaron dos contratos a 12 meses."),
    (5, 2_800_000, 150_000, "Casa llena. Reparación menor en el patio de ropas."),
    (3, 2_200_000, 80_000,
     "Dos unidades desocupadas; se renegoció el canon a la baja mientras se re-arriendan."),
    (5, 2_800_000, 100_000, "Casa llena otra vez tras dos meses de búsqueda."),
    (2, 2_800_000, 200_000,
     "Se fueron tres inquilinos seguidos. Mes en pérdida: entra la reserva."),
    (2, 2_800_000, 150_000,
     "Sigue la vacancia. Segundo mes bajo el equilibrio: se dispara la alerta estructural."),
]

CAPEX_DEMO = [
    (f"{PREFIJO}Amoblado y dotación de zonas comunes", 12_000_000, 60),
    (f"{PREFIJO}Cocina, electrodomésticos y coworking", 6_500_000, 60),
]

# (categoría, descripción, días desde hoy hasta el vencimiento).
# Negativo = vencido; dentro de la ventana de aviso = próximo; lejos = al día.
RECORDATORIOS_DEMO = [
    ("seguro", f"{PREFIJO}Renovar la póliza de arrendamiento", -12),
    ("mantenimiento", f"{PREFIJO}Mantenimiento de calentadores y bombas", 14),
    ("contrato", f"{PREFIJO}Revisar el reajuste anual del canon con la propietaria", 150),
]


def meses_demo(hoy: date | None = None) -> list[tuple[int, int]]:
    """Los 6 meses calendario que terminan en el mes ANTERIOR a hoy, en orden ascendente.

    Se anclan a la fecha actual y no a un año fijo para que la demo no se vea rancia
    dentro de un año.
    """
    hoy = hoy or date.today()
    anio, mes = hoy.year, hoy.month
    meses: list[tuple[int, int]] = []
    for atras in range(6, 0, -1):
        total = (anio * 12 + (mes - 1)) - atras
        meses.append((total // 12, total % 12 + 1))
    return meses


def _fecha(dias: int, hoy: date | None = None) -> str:
    return ((hoy or date.today()) + timedelta(days=dias)).isoformat()


def estado_demo(activo_id: int) -> dict | None:
    """{"fecha": "2026-09-07", "meses": 6} o None si no hay datos de ejemplo cargados."""
    conf = get_configuracion(activo_id)
    marca = conf.get(CLAVE_MARCA)
    if not marca:
        return None
    crudos = [m for m in (conf.get(CLAVE_MESES) or "").split(",") if m.strip()]
    return {"fecha": marca, "meses": len(crudos)}


def _meses_marcados(activo_id: int) -> list[tuple[int, int]]:
    crudo = get_configuracion(activo_id).get(CLAVE_MESES) or ""
    meses = []
    for pieza in crudo.split(","):
        pieza = pieza.strip()
        if not pieza:
            continue
        anio, _, mes = pieza.partition("-")
        try:
            meses.append((int(anio), int(mes)))
        except ValueError:
            continue
    return meses


def cargar_demo(activo_id: int, hoy: date | None = None) -> dict:
    """Carga los seis meses, el capex y los recordatorios de ejemplo, y marca el estado.

    No hace nada si el activo ya tiene meses registrados: la demo nunca se mezcla con
    datos reales.
    """
    if get_reportes(activo_id):
        return {
            "ok": False,
            "meses": 0,
            "capex": 0,
            "recordatorios": 0,
            "error": "El activo ya tiene meses registrados; la demo no se mezcla con datos reales.",
        }

    hoy = hoy or date.today()
    meses = meses_demo(hoy)

    for (anio, mes), (arrendadas, fijos, variables, novedades) in zip(meses, MESES_DEMO):
        unidades = [
            {
                "unidad_label": f"Unidad {i}",
                "arrendada": 1 if i <= arrendadas else 0,
                "ingreso_inquilino": ARRIENDO_UNIDAD if i <= arrendadas else 0.0,
            }
            for i in range(1, 6)
        ]
        ingreso = arrendadas * ARRIENDO_UNIDAD
        guardar_reporte(
            activo_id,
            {
                "mes": mes,
                "anio": anio,
                "gastos_fijos": float(fijos),
                "gastos_variables": float(variables),
                "comision_admin": ingreso * 0.10,
                "novedades": f"{PREFIJO}{novedades}",
                "fecha_registro": hoy.isoformat(),
            },
            unidades,
        )

    primer_anio, primer_mes = meses[0]
    for concepto, monto, horizonte in CAPEX_DEMO:
        agregar_capex(
            activo_id,
            {
                "concepto": concepto,
                "monto": float(monto),
                "fecha": date(primer_anio, primer_mes, 1).isoformat(),
                "horizonte_meses": horizonte,
            },
        )

    for categoria, descripcion, dias in RECORDATORIOS_DEMO:
        datos = {
            "categoria": categoria,
            "descripcion": descripcion,
            "ultima_fecha": None,
            "frecuencia_meses": None,
            "fecha_vencimiento_fija": _fecha(dias, hoy),
            "proxima_fecha": None,
        }
        datos["proxima_fecha"] = calcular_proxima_fecha(datos).isoformat()
        agregar_recordatorio(activo_id, datos)

    set_configuracion(activo_id, CLAVE_MARCA, hoy.isoformat())
    set_configuracion(
        activo_id, CLAVE_MESES, ",".join(f"{a}-{m}" for a, m in meses)
    )
    recalcular_reserva(activo_id)

    return {
        "ok": True,
        "meses": len(meses),
        "capex": len(CAPEX_DEMO),
        "recordatorios": len(RECORDATORIOS_DEMO),
        "error": None,
    }


def limpiar_demo(activo_id: int) -> dict:
    """Borra solo lo que cargó `cargar_demo`: los meses que quedaron marcados y las filas
    con el prefijo. Nunca hace un DELETE a secas sobre el activo."""
    if not estado_demo(activo_id):
        return {"ok": False, "meses": 0, "capex": 0, "recordatorios": 0,
                "error": "No hay datos de ejemplo cargados."}

    meses = _meses_marcados(activo_id)
    for anio, mes in meses:
        eliminar_reporte(activo_id, anio, mes)
        eliminar_asesoria(activo_id, anio, mes)

    capex = [c for c in get_capex(activo_id) if (c["concepto"] or "").startswith(PREFIJO)]
    for c in capex:
        eliminar_capex(activo_id, c["id"])

    recordatorios = [
        r for r in get_recordatorios(activo_id)
        if (r["descripcion"] or "").startswith(PREFIJO)
    ]
    for r in recordatorios:
        eliminar_recordatorio(activo_id, r["id"])

    borrar_configuracion(activo_id, CLAVE_MARCA)
    borrar_configuracion(activo_id, CLAVE_MESES)
    recalcular_reserva(activo_id)

    return {
        "ok": True,
        "meses": len(meses),
        "capex": len(capex),
        "recordatorios": len(recordatorios),
        "error": None,
    }


def umbrales_distintos(activo_id: int) -> dict[str, str]:
    """Umbrales del usuario que no coinciden con los que asume el dataset. Sirve para
    avisar por consola, no para fallar: la demo se carga igual."""
    conf = get_configuracion(activo_id)
    distintos = {}
    for clave, esperado in UMBRALES_ASUMIDOS.items():
        actual = conf.get(clave)
        if actual is None:
            continue
        try:
            if float(actual) != float(esperado):
                distintos[clave] = f"{actual} (la demo asume {esperado})"
        except ValueError:
            distintos[clave] = f"{actual} (la demo asume {esperado})"
    return distintos


def activo_por_defecto() -> int | None:
    activo = get_activo()
    return activo["id"] if activo else None
