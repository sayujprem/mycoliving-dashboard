"""Migra la base SQLite de la version de un solo usuario a una cuenta en PostgreSQL.

Se corre una vez, desde el equipo donde esta mycoliving.db:

    DATABASE_URL=... .venv/bin/python -m scripts.migrar_a_postgres \\
        --sqlite mycoliving.db --email tu@correo.com

Si la cuenta no existe, la crea verificada y como administradora (pide la contrasena
por teclado; no se escribe en la linea de comandos porque quedaria en el historial).

Garantias:
- **Todo o nada.** Las diez tablas se copian en una sola transaccion. Si algo falla a
  mitad, no queda nada escrito.
- **No duplica.** Si la cuenta ya tiene un activo, se niega a correr.
- **Verifica.** Al terminar compara, tabla por tabla, las filas de origen con las de
  destino. Si no cuadran, deshace todo.
- **Respeta el aislamiento.** Las filas de negocio se escriben con el mismo rol acotado
  que usa la aplicacion, asi que es la base misma la que garantiza que quedan bajo la
  cuenta indicada.

Conversiones: los identificadores se regeneran (y se remapean las referencias de
reporte_unidad a su reporte), 0/1 pasa a booleano, y el texto de las fechas lo
interpreta Postgres como DATE. La clave `respaldo_ultimo` de la configuracion se omite:
era el estado del respaldo local y ya no significa nada.
"""
from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from config import DB_ROL_APP
from db.connection import get_connection
from db.init_db import init_db
from db.usuarios import (
    crear_usuario,
    get_usuario_por_email,
    marcar_email_verificado,
    set_asesoria_habilitada,
)

CLAVES_OMITIDAS = {"respaldo_ultimo"}

# Tabla -> (columnas a copiar, columnas booleanas). activo y reporte_unidad se tratan
# aparte porque cambian de padre.
TABLAS_POR_ACTIVO = {
    "contrato_maestro": (
        ("canon_mensual", "fecha_inicio", "fecha_vencimiento", "vigencia_meses",
         "regla_reajuste", "ventana_preaviso_dias", "fecha_definicion"), ()),
    "politica_distribucion": (
        ("porcentaje_libre", "porcentaje_reinversion", "porcentaje_reserva",
         "tarifa_marginal_actual", "calcular_impuesto", "fecha_definicion"), ("calcular_impuesto",)),
    "configuracion_dominio": (("clave", "valor", "descripcion"), ()),
    "capex": (("concepto", "monto", "fecha", "horizonte_meses"), ()),
    "recordatorios": (
        ("categoria", "descripcion", "ultima_fecha", "frecuencia_meses",
         "fecha_vencimiento_fija", "proxima_fecha"), ()),
    "reserva_movimiento": (("mes", "anio", "monto", "saldo_resultante"), ()),
    "asesoria_generada": (
        ("mes", "anio", "semaforo_resultado", "semaforo_ocupacion", "resultado_mes",
         "ocupacion_equilibrio", "porcentaje_libre_real", "brecha_frente_a_meta",
         "capex_recuperado_pct", "texto_asesoria", "texto_fiscal", "fecha_generacion"), ()),
}
CAMPOS_ACTIVO = ("nombre", "tipo", "unidades_totales", "comision_administrador_pct",
                 "moneda", "ubicacion", "notas")
CAMPOS_REPORTE = ("mes", "anio", "gastos_fijos", "gastos_variables", "comision_admin",
                  "novedades", "fecha_registro")


class MigracionAbortada(Exception):
    pass


def _insertar(cur, tabla: str, columnas: tuple, valores: tuple, devolver_id: bool = False):
    marcas = ", ".join(["%s"] * len(columnas))
    sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcas})"
    cur.execute(sql + (" RETURNING id" if devolver_id else ""), valores)
    return cur.fetchone()["id"] if devolver_id else None


def _fila(fila: sqlite3.Row, columnas: tuple, booleanas: tuple = ()) -> tuple:
    return tuple(bool(fila[c]) if c in booleanas else fila[c] for c in columnas)


def migrar(ruta_sqlite: Path, usuario_id: int) -> dict[str, tuple[int, int]]:
    """Copia todo y devuelve {tabla: (filas_origen, filas_destino)}."""
    # Solo lectura: la migracion no puede alterar el archivo de origen ni por accidente.
    origen = sqlite3.connect(f"file:{ruta_sqlite.resolve()}?mode=ro", uri=True)
    origen.row_factory = sqlite3.Row
    try:
        activos = origen.execute("SELECT * FROM activo").fetchall()
        if len(activos) != 1:
            raise MigracionAbortada(f"Se esperaba un activo en la base de origen y hay {len(activos)}.")
        viejo = activos[0]

        conn = get_connection()
        try:
            with conn:  # una sola transaccion: commit al final o rollback ante cualquier error
                with conn.cursor() as cur:
                    cur.execute(f"SET LOCAL ROLE {DB_ROL_APP}")
                    cur.execute("SELECT set_config('app.usuario_id', %s, true)", (str(usuario_id),))

                    cur.execute("SELECT 1 FROM activo WHERE usuario_id = %s", (usuario_id,))
                    if cur.fetchone():
                        raise MigracionAbortada("La cuenta ya tiene un activo. No se migra nada para no duplicar.")

                    activo_id = _insertar(
                        cur, "activo", ("usuario_id", *CAMPOS_ACTIVO),
                        (usuario_id, *_fila(viejo, CAMPOS_ACTIVO)), devolver_id=True,
                    )
                    conteo: dict[str, tuple[int, int]] = {"activo": (1, 1)}

                    for tabla, (columnas, booleanas) in TABLAS_POR_ACTIVO.items():
                        filas = origen.execute(
                            f"SELECT * FROM {tabla} WHERE activo_id = ? ORDER BY id", (viejo["id"],)
                        ).fetchall()
                        if tabla == "configuracion_dominio":
                            filas = [f for f in filas if f["clave"] not in CLAVES_OMITIDAS]
                        for f in filas:
                            _insertar(cur, tabla, ("activo_id", *columnas),
                                      (activo_id, *_fila(f, columnas, booleanas)))
                        cur.execute(f"SELECT count(*) AS n FROM {tabla} WHERE activo_id = %s", (activo_id,))
                        conteo[tabla] = (len(filas), cur.fetchone()["n"])

                    # reporte_mensual y sus unidades: los ids cambian, asi que se remapean.
                    reportes = origen.execute(
                        "SELECT * FROM reporte_mensual WHERE activo_id = ? ORDER BY id", (viejo["id"],)
                    ).fetchall()
                    unidades_origen = 0
                    for rep in reportes:
                        nuevo_id = _insertar(
                            cur, "reporte_mensual", ("activo_id", *CAMPOS_REPORTE),
                            (activo_id, *_fila(rep, CAMPOS_REPORTE)), devolver_id=True,
                        )
                        unidades = origen.execute(
                            "SELECT * FROM reporte_unidad WHERE reporte_mensual_id = ? ORDER BY id", (rep["id"],)
                        ).fetchall()
                        unidades_origen += len(unidades)
                        for u in unidades:
                            _insertar(
                                cur, "reporte_unidad",
                                ("reporte_mensual_id", "unidad_label", "arrendada", "ingreso_inquilino"),
                                (nuevo_id, u["unidad_label"], bool(u["arrendada"]), u["ingreso_inquilino"]),
                            )
                    cur.execute("SELECT count(*) AS n FROM reporte_mensual WHERE activo_id = %s", (activo_id,))
                    conteo["reporte_mensual"] = (len(reportes), cur.fetchone()["n"])
                    cur.execute(
                        "SELECT count(*) AS n FROM reporte_unidad u JOIN reporte_mensual r "
                        "ON r.id = u.reporte_mensual_id WHERE r.activo_id = %s", (activo_id,),
                    )
                    conteo["reporte_unidad"] = (unidades_origen, cur.fetchone()["n"])

                    descuadres = {t: c for t, c in conteo.items() if c[0] != c[1]}
                    if descuadres:
                        raise MigracionAbortada(f"Los conteos no cuadran, se deshace todo: {descuadres}")
                    return conteo
        finally:
            conn.close()
    finally:
        origen.close()


def _cuenta(email: str) -> int:
    usuario = get_usuario_por_email(email)
    if usuario:
        print(f"Se usará la cuenta existente {usuario['email']}.")
        return usuario["id"]
    print(f"La cuenta {email} no existe. Se creará verificada y como administradora.")
    while True:
        clave = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
        if len(clave) >= 10 and clave == getpass.getpass("Repítela: "):
            break
        print("No cumple el mínimo o no coincide. Otra vez.")
    usuario_id = crear_usuario(email, clave, es_admin=True)
    marcar_email_verificado(usuario_id)
    set_asesoria_habilitada(usuario_id, True)
    return usuario_id


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sqlite", type=Path, required=True, help="ruta de mycoliving.db")
    p.add_argument("--email", required=True, help="correo de la cuenta de destino")
    args = p.parse_args()

    if not args.sqlite.exists():
        print(f"No existe {args.sqlite}.")
        return 1

    init_db()
    usuario_id = _cuenta(args.email)
    try:
        conteo = migrar(args.sqlite, usuario_id)
    except MigracionAbortada as exc:
        print(f"Migración abortada, no se escribió nada. {exc}")
        return 1

    print("\nMigración completa. Filas por tabla (origen = destino):")
    for tabla, (n, _) in conteo.items():
        print(f"  {tabla:24s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
