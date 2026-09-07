"""Prepara los recordatorios del activo para mostrarlos: próxima fecha y estado.

Las categorías salen de `configuracion_dominio` (`categorias_recordatorio`), no de una lista
fija en el código.
"""
from __future__ import annotations

from datetime import date

from dominio.configuracion import ventana_aviso
from motor.recordatorios import EstadoRecordatorio, clasificar, proxima_fecha


def _fecha(valor) -> date | None:
    if not valor:
        return None
    return date.fromisoformat(str(valor)[:10])


def calcular_proxima_fecha(recordatorio) -> date:
    return proxima_fecha(
        _fecha(recordatorio.get("ultima_fecha")),
        recordatorio.get("frecuencia_meses"),
        _fecha(recordatorio.get("fecha_vencimiento_fija")),
    )


def clasificar_recordatorios(recordatorios, configuracion: dict, hoy: date | None = None):
    """Devuelve [(fila, EstadoRecordatorio), ...] ordenado por urgencia."""
    hoy = hoy or date.today()
    ventana = ventana_aviso(configuracion)
    resultado: list[tuple[dict, EstadoRecordatorio]] = []
    for r in recordatorios:
        fila = dict(r)
        prox = _fecha(fila.get("proxima_fecha")) or calcular_proxima_fecha(fila)
        resultado.append((fila, clasificar(prox, hoy, ventana)))
    resultado.sort(key=lambda par: par[1].dias_restantes)
    return resultado
