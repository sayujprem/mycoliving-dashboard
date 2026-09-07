"""Respaldo mensual de la base de datos a Google Drive con rclone.

Está en Python y no en shell por tres razones concretas:

1. `sqlite3.Connection.backup()` produce un snapshot **consistente** aunque uvicorn esté
   escribiendo. Un `cp` del .db a mitad de una transacción puede dar un archivo corrupto
   que solo descubres el día que lo necesitas.
2. Puede dejar el resultado escrito en la propia base, para que se vea en /config.
3. Se puede testear: `ejecutar` es inyectable, así que la suite prueba todos los caminos
   de fallo sin rclone instalado ni tocar la red.

El principio de diseño es que **ningún eslabón falle en silencio**. Un `rclone copy` puede
devolver 0 y no haber subido nada (cuota llena, token vencido), así que después de subir se
verifica que el archivo esté allá y que el tamaño coincida.

Correr a mano:  .venv/bin/python -m scripts.respaldo
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config import BASE_DIR, DB_PATH
from db.repositorio import get_activo, set_configuracion

REMOTO = "gdrive:"
CONSERVAR_EN_DRIVE = 12
CONSERVAR_EN_LOCAL = 3
DIR_RESPALDOS = BASE_DIR / "respaldos"
DIR_LOGS = BASE_DIR / "logs"
ARCHIVO_LOG = DIR_LOGS / "respaldo.log"
CLAVE_ESTADO = "respaldo_ultimo"

RE_RESPALDO = re.compile(r"^mycoliving-\d{4}-\d{2}-\d{2}\.db$")


@dataclass(frozen=True)
class ResultadoRespaldo:
    ok: bool
    nombre: str | None = None
    subidos: int = 0
    rotados: int = 0
    error: str | None = None


def nombre_respaldo(dia: date) -> str:
    return f"mycoliving-{dia.isoformat()}.db"


def sobrantes(nombres: list[str], conservar: int = CONSERVAR_EN_DRIVE) -> list[str]:
    """De una lista de nombres, los respaldos que exceden `conservar`, del más viejo al
    más nuevo. Ignora cualquier archivo que no sea un respaldo nuestro."""
    propios = sorted(n for n in nombres if RE_RESPALDO.match(n.strip()))
    if len(propios) <= conservar:
        return []
    return propios[: len(propios) - conservar]


def snapshot(destino: Path, origen: Path | None = None) -> None:
    """Copia consistente de la base, segura aunque la app esté escribiendo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    fuente = sqlite3.connect(origen or DB_PATH)
    try:
        copia = sqlite3.connect(destino)
        try:
            fuente.backup(copia)
        finally:
            copia.close()
    finally:
        fuente.close()


def _ejecutar_real(args: list[str]) -> tuple[int, str]:
    """Un binario que no existe tiene que devolver un código, no reventar: si no, el
    script muere con un traceback en vez del mensaje accionable, que es justo lo que
    nadie va a leer cuando esto corra solo a las 9 de la noche."""
    try:
        proceso = subprocess.run(args, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return 127, str(exc)
    return proceso.returncode, (proceso.stdout or "") + (proceso.stderr or "")


def _localizar_rclone() -> str | None:
    return os.environ.get("RCLONE_BIN") or shutil.which("rclone")


def respaldar(
    *,
    rclone: str | None = None,
    remoto: str = REMOTO,
    conservar: int = CONSERVAR_EN_DRIVE,
    hoy: date | None = None,
    ejecutar=None,
    db_path: Path | None = None,
) -> ResultadoRespaldo:
    hoy = hoy or date.today()
    correr = ejecutar or _ejecutar_real
    binario = rclone if rclone is not None else _localizar_rclone()

    if not binario:
        return ResultadoRespaldo(
            ok=False,
            error="rclone no está instalado o no está en el PATH. Ver la sección de "
                  "respaldo en el README.",
        )

    codigo, salida = correr([binario, "listremotes"])
    if codigo == 127:
        return ResultadoRespaldo(
            ok=False,
            error=f"No se pudo ejecutar rclone en '{binario}': {salida[:150]}",
        )
    if codigo != 0 or remoto not in salida:
        return ResultadoRespaldo(
            ok=False,
            error=f"El remoto '{remoto.rstrip(':')}' no está configurado. Corre: rclone config",
        )

    # Valida que el token OAuth siga vivo antes de gastar tiempo copiando.
    codigo, salida = correr([binario, "lsd", remoto])
    if codigo != 0:
        return ResultadoRespaldo(
            ok=False,
            error=f"rclone no pudo abrir Drive (¿token vencido?): {salida.strip()[:200]}",
        )

    nombre = nombre_respaldo(hoy)
    local = DIR_RESPALDOS / nombre
    snapshot(local, db_path)
    tamano_local = local.stat().st_size

    codigo, salida = correr([binario, "copyto", str(local), f"{remoto}{nombre}"])
    if codigo != 0:
        return ResultadoRespaldo(
            ok=False, nombre=nombre,
            error=f"Falló la subida a Drive: {salida.strip()[:200]}",
        )

    # El paso que impide el fallo silencioso: un copy con código 0 no garantiza nada.
    codigo, salida = correr([binario, "lsf", remoto, "--include", nombre])
    if codigo != 0 or nombre not in salida:
        return ResultadoRespaldo(
            ok=False, nombre=nombre,
            error="El respaldo no quedó en Drive: rclone dijo que subió, pero el archivo "
                  "no aparece en el destino.",
        )

    codigo, salida = correr([binario, "size", f"{remoto}{nombre}", "--json"])
    if codigo == 0:
        encontrado = re.search(r'"bytes"\s*:\s*(\d+)', salida)
        if encontrado and int(encontrado.group(1)) != tamano_local:
            return ResultadoRespaldo(
                ok=False, nombre=nombre,
                error=f"El archivo en Drive pesa {encontrado.group(1)} bytes y el local "
                      f"{tamano_local}: la subida quedó incompleta.",
            )

    rotados = 0
    codigo, salida = correr([binario, "lsf", remoto, "--include", "mycoliving-*.db"])
    if codigo == 0:
        for viejo in sobrantes([l.strip() for l in salida.splitlines()], conservar):
            if correr([binario, "deletefile", f"{remoto}{viejo}"])[0] == 0:
                rotados += 1

    _rotar_local()
    return ResultadoRespaldo(ok=True, nombre=nombre, subidos=1, rotados=rotados)


def _rotar_local() -> None:
    if not DIR_RESPALDOS.exists():
        return
    propios = sorted(p for p in DIR_RESPALDOS.iterdir() if RE_RESPALDO.match(p.name))
    for viejo in propios[:-CONSERVAR_EN_LOCAL] if len(propios) > CONSERVAR_EN_LOCAL else []:
        viejo.unlink(missing_ok=True)


def registrar_estado(resultado: ResultadoRespaldo, hoy: date | None = None) -> str:
    """Deja el resultado donde el usuario ya mira: la pantalla de configuración.

    Una notificación de macOS se pierde; una línea en /config, no.
    """
    hoy = hoy or date.today()
    if resultado.ok:
        texto = f"{hoy.isoformat()} · ok"
        if resultado.rotados:
            texto += f" · {resultado.rotados} copias viejas eliminadas"
    else:
        texto = f"{hoy.isoformat()} · ERROR: {resultado.error}"

    activo = get_activo()
    if activo:
        set_configuracion(activo["id"], CLAVE_ESTADO, texto)
    return texto


def _log(texto: str) -> None:
    DIR_LOGS.mkdir(parents=True, exist_ok=True)
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(texto + "\n")


def _avisar(mensaje: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{mensaje[:180]}" with title "MyColiving: falló el respaldo"'],
            capture_output=True,
        )
    except Exception:
        pass  # el aviso es un extra; el registro en /config y el log son lo que manda


def main() -> int:
    resultado = respaldar()
    texto = registrar_estado(resultado)
    _log(texto)
    print(texto)
    if not resultado.ok:
        _avisar(resultado.error or "error desconocido")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
