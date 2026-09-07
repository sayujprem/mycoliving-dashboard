"""Catálogo de umbrales de dominio: qué es "óptimo" para este tipo de activo.

Aquí solo viven las CLAVES y su descripción. Los VALORES los define el usuario desde la
interfaz y se guardan en la tabla `configuracion_dominio`. Ningún umbral numérico se escribe
en el código.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaveConfig:
    clave: str
    etiqueta: str
    descripcion: str
    tipo: str  # "int" | "float" | "texto"


CLAVES_CONFIGURACION: list[ClaveConfig] = [
    ClaveConfig(
        "ocupacion_minima_verde",
        "Ocupación mínima para verde",
        "Unidades arrendadas desde las cuales el semáforo de ocupación se pone en verde.",
        "int",
    ),
    ClaveConfig(
        "gasto_maximo_pct_verde",
        "Gasto máximo para verde (%)",
        "Porcentaje del ingreso que pueden consumir la comisión y TODOS los gastos del "
        "informe sin que el semáforo de resultado deje de estar verde. Calíbralo según "
        "dónde esté el canon de la propietaria: si va dentro de los gastos fijos, el "
        "umbral tiene que ser alto (≈80); si lo separas en un contrato maestro, bajo "
        "(≈45). Para afinarlo, toma un mes bueno y calcula "
        "(comisión + gastos fijos + gastos variables) ÷ ingreso.",
        "float",
    ),
    ClaveConfig(
        "meses_consecutivos_baja_ocupacion_para_rojo",
        "Meses seguidos de baja ocupación para rojo",
        "Cuántos meses consecutivos por debajo de la ocupación de equilibrio disparan el "
        "rojo por riesgo de vacancia.",
        "int",
    ),
    ClaveConfig(
        "arriendo_promedio_unidad",
        "Arriendo promedio por unidad",
        "Lo que en promedio cobras de subarriendo por cada unidad. Se usa para calcular la "
        "ocupación de equilibrio.",
        "float",
    ),
    ClaveConfig(
        "ventana_aviso_recordatorio_dias",
        "Ventana de aviso de recordatorios (días)",
        "Con cuántos días de anticipación un recordatorio pasa de 'al día' a 'próximo'.",
        "int",
    ),
    ClaveConfig(
        "categorias_recordatorio",
        "Categorías de recordatorio",
        "Lista separada por comas. Son las etiquetas disponibles al crear un recordatorio "
        "(ej. mantenimiento, seguro, contrato).",
        "texto",
    ),
    ClaveConfig(
        "horizonte_meses",
        "Horizonte temporal (meses)",
        "La ventana con la que miras el activo. Se usa para el ritmo de recuperación del "
        "capex y para enmarcar la asesoría. Ajustable en cualquier momento.",
        "int",
    ),
    ClaveConfig(
        "horizonte_destino",
        "Destino declarado del horizonte",
        "En una frase, qué esperas de este activo en ese horizonte (ej. renta estable sin "
        "venta prevista, o soltar el contrato en 2 años).",
        "texto",
    ),
]

HORIZONTE_POR_DEFECTO_MESES = 60

VENTANA_AVISO_POR_DEFECTO = 30  # días; solo si no hay valor en configuracion_dominio


def ventana_aviso(configuracion: dict) -> int:
    crudo = (configuracion.get("ventana_aviso_recordatorio_dias") or "").strip()
    try:
        return int(float(crudo))
    except ValueError:
        return VENTANA_AVISO_POR_DEFECTO


def categorias_recordatorio(configuracion: dict) -> list[str]:
    crudo = configuracion.get("categorias_recordatorio") or ""
    return [c.strip() for c in crudo.split(",") if c.strip()]


def leer_numero(configuracion: dict, clave: str, defecto: float = 0.0) -> float:
    try:
        return float(configuracion.get(clave))
    except (TypeError, ValueError):
        return defecto


def leer_entero(configuracion: dict, clave: str, defecto: int = 0) -> int:
    try:
        return int(float(configuracion.get(clave)))
    except (TypeError, ValueError):
        return defecto


def horizonte_meses(configuracion: dict) -> int:
    valor = leer_entero(configuracion, "horizonte_meses", HORIZONTE_POR_DEFECTO_MESES)
    return valor if valor > 0 else HORIZONTE_POR_DEFECTO_MESES


def horizonte_destino(configuracion: dict) -> str:
    return (configuracion.get("horizonte_destino") or "").strip()
