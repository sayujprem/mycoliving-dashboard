"""Agrega la recuperación de todas las partidas de capex del activo.

Cada partida tiene su fecha y su horizonte. Los meses transcurridos se cuentan desde la
fecha de la partida hasta una fecha de referencia (por defecto, hoy).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from motor.capex import RecuperacionCapex, recuperacion


@dataclass(frozen=True)
class ResumenCapex:
    monto_total: float
    recuperado: float
    pendiente: float
    pct_recuperado: float
    detalle: list[tuple[dict, RecuperacionCapex]]


def _meses_transcurridos(desde_iso: str, hasta: date) -> int:
    d = date.fromisoformat(desde_iso)
    return (hasta.year - d.year) * 12 + (hasta.month - d.month)


def resumen_capex(partidas, hasta: date | None = None) -> ResumenCapex:
    hasta = hasta or date.today()
    detalle: list[tuple[dict, RecuperacionCapex]] = []
    monto_total = 0.0
    recuperado = 0.0
    for p in partidas:
        rec = recuperacion(
            p["monto"], p["horizonte_meses"], _meses_transcurridos(p["fecha"], hasta)
        )
        detalle.append((dict(p) if not isinstance(p, dict) else p, rec))
        monto_total += rec.monto_total
        recuperado += rec.recuperado
    pct = (recuperado / monto_total * 100) if monto_total else 0.0
    return ResumenCapex(
        monto_total=monto_total,
        recuperado=recuperado,
        pendiente=monto_total - recuperado,
        pct_recuperado=pct,
        detalle=detalle,
    )
