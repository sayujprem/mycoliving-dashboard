"""Respaldo mensual de la base a Google Drive: pg_dump, cifrado con gpg y subida con rclone.

Corre en GitHub Actions (.github/workflows/respaldo.yml). Tambien se puede correr a mano
con las mismas variables de entorno:  .venv/bin/python -m scripts.respaldo

El principio de diseno es que **ningun eslabon falle en silencio**. Un `rclone copy`
puede devolver 0 y no haber subido nada (cuota llena, token vencido), asi que despues de
subir se verifica que el archivo este alla y que el tamano coincida.

**El respaldo sale siempre cifrado.** Contiene los datos de todas las cuentas: correos,
hashes de contrasenas y la informacion financiera de cada activo. Si falta la clave de
cifrado, el respaldo falla; nunca se sube en claro.

Variables:
    DATABASE_URL_RESPALDO  conexion al *session pooler* de Supabase (puerto 5432).
                           pg_dump no funciona por el transaction pooler que usa la app.
    RESPALDO_CLAVE         frase para cifrar. Sin ella no hay forma de leer las copias:
                           guardala tambien fuera de GitHub.
    RESPALDO_REMOTO        destino en rclone. Por defecto "respaldos:mycoliving/": el
                           remoto "respaldos" y, dentro, la carpeta "mycoliving", que
                           rclone crea en la primera subida.

Restaurar una copia:
    gpg --decrypt mycoliving-AAAA-MM-DD.dump.gpg > copia.dump
    pg_restore --no-owner --clean --if-exists -d "$DATABASE_URL_RESPALDO" copia.dump

Esta en Python y no en shell para poder probarlo: `ejecutar` es inyectable, asi que la
suite recorre todos los caminos de fallo sin pg_dump, gpg, rclone ni red.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REMOTO = os.environ.get("RESPALDO_REMOTO", "respaldos:mycoliving/")
CONSERVAR_EN_DRIVE = 12

RE_RESPALDO = re.compile(r"^mycoliving-\d{4}-\d{2}-\d{2}\.dump\.gpg$")


@dataclass(frozen=True)
class ResultadoRespaldo:
    ok: bool
    nombre: str | None = None
    subidos: int = 0
    rotados: int = 0
    error: str | None = None


def nombre_respaldo(dia: date) -> str:
    return f"mycoliving-{dia.isoformat()}.dump.gpg"


def sobrantes(nombres: list[str], conservar: int = CONSERVAR_EN_DRIVE) -> list[str]:
    """De una lista de nombres, los respaldos que exceden `conservar`, del más viejo al
    más nuevo. Ignora cualquier archivo que no sea un respaldo nuestro."""
    propios = sorted(n for n in nombres if RE_RESPALDO.match(n.strip()))
    if len(propios) <= conservar:
        return []
    return propios[: len(propios) - conservar]


def _ejecutar_real(args: list[str], entrada: str | None = None) -> tuple[int, str]:
    """Un binario que no existe tiene que devolver un código, no reventar: si no, el
    script muere con un traceback en vez del mensaje accionable."""
    try:
        proceso = subprocess.run(args, capture_output=True, text=True, input=entrada)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return 127, str(exc)
    return proceso.returncode, (proceso.stdout or "") + (proceso.stderr or "")


def _binario(nombre: str) -> str | None:
    return os.environ.get(f"{nombre.upper()}_BIN") or shutil.which(nombre)


def respaldar(
    *,
    url: str | None = None,
    clave: str | None = None,
    remoto: str = REMOTO,
    conservar: int = CONSERVAR_EN_DRIVE,
    hoy: date | None = None,
    ejecutar=None,
    binarios: dict[str, str | None] | None = None,
    directorio: Path | None = None,
) -> ResultadoRespaldo:
    hoy = hoy or date.today()
    correr = ejecutar or _ejecutar_real
    # "respaldos:carpeta" y "respaldos:carpeta/" deben significar lo mismo; sin la barra,
    # el nombre del archivo quedaria pegado al de la carpeta.
    if not remoto.endswith((":", "/")):
        remoto += "/"
    raiz = remoto.split(":", 1)[0] + ":"
    url = url if url is not None else os.environ.get("DATABASE_URL_RESPALDO", "")
    clave = clave if clave is not None else os.environ.get("RESPALDO_CLAVE", "")
    binarios = binarios if binarios is not None else {
        b: _binario(b) for b in ("pg_dump", "gpg", "rclone")
    }

    # --- precondiciones: se comprueba todo antes de tocar nada -----------------
    if not url:
        return ResultadoRespaldo(ok=False, error="Falta DATABASE_URL_RESPALDO (session pooler, puerto 5432).")
    if not clave:
        return ResultadoRespaldo(
            ok=False,
            error="Falta RESPALDO_CLAVE. El respaldo contiene datos de todas las cuentas "
                  "y no se sube sin cifrar.",
        )
    for nombre in ("pg_dump", "gpg", "rclone"):
        if not binarios.get(nombre):
            return ResultadoRespaldo(ok=False, error=f"{nombre} no está instalado o no está en el PATH.")
    pg_dump, gpg, rclone = binarios["pg_dump"], binarios["gpg"], binarios["rclone"]

    codigo, salida = correr([rclone, "listremotes"])
    if codigo == 127:
        return ResultadoRespaldo(ok=False, error=f"No se pudo ejecutar rclone en '{rclone}': {salida[:150]}")
    if codigo != 0 or raiz not in salida:
        return ResultadoRespaldo(
            ok=False,
            error=f"El remoto '{raiz.rstrip(':')}' no está configurado en rclone.",
        )

    # Valida que el token OAuth siga vivo antes de gastar tiempo volcando la base. Se
    # lista la raiz y no la carpeta de destino: en la primera corrida esa carpeta aun no
    # existe (la crea la subida) y el lsd fallaria como si el token estuviera vencido.
    codigo, salida = correr([rclone, "lsd", raiz])
    if codigo != 0:
        return ResultadoRespaldo(
            ok=False, error=f"rclone no pudo abrir Drive (¿token vencido?): {salida.strip()[:200]}"
        )

    nombre = nombre_respaldo(hoy)
    with tempfile.TemporaryDirectory(dir=directorio) as tmp:
        volcado = Path(tmp) / "volcado.dump"
        cifrado = Path(tmp) / nombre

        # --- volcado -----------------------------------------------------------
        # Formato custom: comprimido y restaurable por partes con pg_restore.
        # Solo el esquema public: Supabase guarda en otros esquemas cosas suyas
        # (auth, storage) que no son de esta aplicacion.
        codigo, salida = correr([
            pg_dump, "--format=custom", "--no-owner", "--no-privileges",
            "--schema=public", f"--file={volcado}", url,
        ])
        if codigo != 0 or not volcado.exists() or volcado.stat().st_size == 0:
            # La salida de pg_dump puede incluir la cadena de conexion; no se muestra.
            return ResultadoRespaldo(ok=False, nombre=nombre, error="pg_dump no pudo volcar la base.")

        # --- cifrado -----------------------------------------------------------
        # La frase entra por stdin y no como argumento: los argumentos de un proceso
        # los puede leer cualquier otro proceso de la maquina.
        codigo, salida = correr(
            [gpg, "--batch", "--yes", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
             "--symmetric", "--cipher-algo", "AES256", "--output", str(cifrado), str(volcado)],
            entrada=clave,
        )
        volcado.unlink(missing_ok=True)  # la copia en claro no sobrevive al cifrado
        if codigo != 0 or not cifrado.exists():
            return ResultadoRespaldo(ok=False, nombre=nombre, error=f"gpg no pudo cifrar el volcado: {salida.strip()[:200]}")
        tamano_local = cifrado.stat().st_size

        # --- subida y verificacion ---------------------------------------------
        codigo, salida = correr([rclone, "copyto", str(cifrado), f"{remoto}{nombre}"])
        if codigo != 0:
            return ResultadoRespaldo(ok=False, nombre=nombre, error=f"Falló la subida a Drive: {salida.strip()[:200]}")

    # El paso que impide el fallo silencioso: un copy con código 0 no garantiza nada.
    codigo, salida = correr([rclone, "lsf", remoto, "--include", nombre])
    if codigo != 0 or nombre not in salida:
        return ResultadoRespaldo(
            ok=False, nombre=nombre,
            error="El respaldo no quedó en Drive: rclone dijo que subió, pero el archivo "
                  "no aparece en el destino.",
        )

    codigo, salida = correr([rclone, "size", f"{remoto}{nombre}", "--json"])
    if codigo == 0:
        encontrado = re.search(r'"bytes"\s*:\s*(\d+)', salida)
        if encontrado and int(encontrado.group(1)) != tamano_local:
            return ResultadoRespaldo(
                ok=False, nombre=nombre,
                error=f"El archivo en Drive pesa {encontrado.group(1)} bytes y el local "
                      f"{tamano_local}: la subida quedó incompleta.",
            )

    rotados = 0
    codigo, salida = correr([rclone, "lsf", remoto, "--include", "mycoliving-*.dump.gpg"])
    if codigo == 0:
        for viejo in sobrantes([linea.strip() for linea in salida.splitlines()], conservar):
            if correr([rclone, "deletefile", f"{remoto}{viejo}"])[0] == 0:
                rotados += 1

    return ResultadoRespaldo(ok=True, nombre=nombre, subidos=1, rotados=rotados)


def main() -> int:
    resultado = respaldar()
    if resultado.ok:
        texto = f"{date.today().isoformat()} · ok · {resultado.nombre}"
        if resultado.rotados:
            texto += f" · {resultado.rotados} copias viejas eliminadas"
        print(texto)
        return 0
    # En GitHub Actions un codigo distinto de cero marca el job en rojo y GitHub avisa
    # por correo. Ese es el aviso: no hace falta otro.
    print(f"{date.today().isoformat()} · ERROR: {resultado.error}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
