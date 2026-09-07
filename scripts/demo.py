"""Cargar y quitar los datos de ejemplo del dashboard.

Sirve para ver la plataforma entera funcionando antes de tener cifras reales: seis meses
que recorren los tres colores del semáforo, capex y recordatorios en sus tres estados.

Correr:
    python -m scripts.demo cargar
    python -m scripts.demo limpiar
    python -m scripts.demo estado

Convive con `seed_coliving.py`, no lo reemplaza: el seed deja el activo y los umbrales
(datos de arranque real), esta demo deja el movimiento de ejemplo. `cargar` llama al seed
primero, que es no-op si ya hay un activo.
"""
import sys

from dominio.demo import (
    activo_por_defecto,
    cargar_demo,
    estado_demo,
    limpiar_demo,
    umbrales_distintos,
)
from scripts.seed_coliving import seed


def _activo_id() -> int | None:
    activo_id = activo_por_defecto()
    if not activo_id:
        print("No hay un activo configurado. Corre primero: python -m scripts.seed_coliving")
    return activo_id


def cargar() -> int:
    seed()  # no-op si ya hay activo
    activo_id = _activo_id()
    if not activo_id:
        return 1

    distintos = umbrales_distintos(activo_id)
    if distintos:
        print("Aviso: tus umbrales no son los que asume la demo, así que los colores")
        print("pueden variar respecto a lo documentado:")
        for clave, detalle in distintos.items():
            print(f"  - {clave}: {detalle}")
        print()

    r = cargar_demo(activo_id)
    if not r["ok"]:
        print(f"No se cargó nada: {r['error']}")
        return 1
    print(f"Datos de ejemplo cargados: {r['meses']} meses, {r['capex']} partidas de capex, "
          f"{r['recordatorios']} recordatorios.")
    print("El panel avisa que son datos de ejemplo. Para quitarlos:")
    print("  python -m scripts.demo limpiar   (o el botón del banner en el panel)")
    return 0


def limpiar() -> int:
    activo_id = _activo_id()
    if not activo_id:
        return 1
    r = limpiar_demo(activo_id)
    if not r["ok"]:
        print(r["error"])
        return 0
    print(f"Datos de ejemplo eliminados: {r['meses']} meses, {r['capex']} partidas de capex, "
          f"{r['recordatorios']} recordatorios. Lo que hayas cargado tú sigue intacto.")
    return 0


def estado() -> int:
    activo_id = _activo_id()
    if not activo_id:
        return 1
    e = estado_demo(activo_id)
    if not e:
        print("No hay datos de ejemplo cargados.")
    else:
        print(f"Datos de ejemplo cargados el {e['fecha']}: {e['meses']} meses.")
    return 0


COMANDOS = {"cargar": cargar, "limpiar": limpiar, "estado": estado}


def main() -> int:
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando not in COMANDOS:
        print(f"Uso: python -m scripts.demo [{' | '.join(COMANDOS)}]")
        return 2
    return COMANDOS[comando]()


if __name__ == "__main__":
    raise SystemExit(main())
