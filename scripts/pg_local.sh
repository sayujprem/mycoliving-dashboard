#!/usr/bin/env bash
# Postgres local para desarrollo y pruebas, sin Docker ni Homebrew.
#
# Descarga los binarios oficiales de PostgreSQL que publica el proyecto zonky en Maven
# Central y los deja en .pg/ (ignorada por git). Nada se instala en el sistema: borrar
# la carpeta .pg/ lo deshace todo.
#
# Uso:
#   scripts/pg_local.sh start   # descarga la primera vez, inicializa y arranca
#   scripts/pg_local.sh stop
#   scripts/pg_local.sh url     # imprime la DATABASE_URL para .env
#
# La version coincide con la mayor de Supabase (17) para que las pruebas locales
# se comporten igual que produccion.
set -euo pipefail

VERSION="17.11.0"
PUERTO="54329"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)/.pg"
BIN="$RAIZ/bin"
DATOS="$RAIZ/datos"
LOG="$RAIZ/postgres.log"

case "$(uname -s)-$(uname -m)" in
  Darwin-x86_64) PLATAFORMA="darwin-amd64" ;;
  Darwin-arm64)  PLATAFORMA="darwin-arm64v8" ;;
  Linux-x86_64)  PLATAFORMA="linux-amd64" ;;
  Linux-aarch64) PLATAFORMA="linux-arm64v8" ;;
  *) echo "Plataforma no soportada: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

descargar() {
  [ -x "$BIN/pg_ctl" ] && return
  mkdir -p "$RAIZ"
  local artefacto="embedded-postgres-binaries-$PLATAFORMA"
  local url="https://repo1.maven.org/maven2/io/zonky/test/postgres/$artefacto/$VERSION/$artefacto-$VERSION.jar"
  echo "Descargando PostgreSQL $VERSION ($PLATAFORMA)..."
  curl -fsSL "$url" -o "$RAIZ/pg.jar"
  # El .jar es un zip que contiene un .txz con bin/, lib/ y share/.
  (cd "$RAIZ" && unzip -q -o pg.jar '*.txz' && tar -xJf ./*.txz && rm -f pg.jar ./*.txz)
}

inicializar() {
  [ -f "$DATOS/PG_VERSION" ] && return
  "$BIN/initdb" -D "$DATOS" -U postgres --auth=trust --encoding=UTF8 --locale=C >/dev/null
}

case "${1:-}" in
  start)
    descargar
    inicializar
    if "$BIN/pg_ctl" -D "$DATOS" status >/dev/null 2>&1; then
      echo "Ya estaba corriendo en el puerto $PUERTO."
    else
      "$BIN/pg_ctl" -D "$DATOS" -l "$LOG" -o "-p $PUERTO -k /tmp" -w start >/dev/null
      echo "PostgreSQL corriendo en el puerto $PUERTO."
    fi
    # Los binarios de zonky traen solo el servidor (sin psql ni createdb), asi que
    # las bases se crean con psycopg, que ya es dependencia del proyecto.
    PY="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
    "$PY" - "$PUERTO" <<'PYEOF'
import sys
import psycopg

with psycopg.connect(f"postgresql://postgres@localhost:{sys.argv[1]}/postgres", autocommit=True) as c:
    for base in ("mycoliving", "mycoliving_test"):
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (base,)).fetchone():
            c.execute(f'CREATE DATABASE "{base}"')
            print(f"Base {base} creada.")
PYEOF
    ;;
  stop)
    "$BIN/pg_ctl" -D "$DATOS" -w stop >/dev/null && echo "PostgreSQL detenido."
    ;;
  url)
    echo "postgresql://postgres@localhost:$PUERTO/mycoliving"
    ;;
  *)
    echo "Uso: $0 {start|stop|url}" >&2
    exit 2
    ;;
esac
