"""Acceso a datos. Capa de persistencia: ni motor ni dominio, solo lectura/escritura.

En esta versión hay un solo activo, así que `get_activo()` devuelve el primero que exista.
Las tablas ya llevan `activo_id` para no encarecer el multi-activo más adelante.
"""
import sqlite3

from db.connection import db_cursor, get_connection

CAMPOS_ACTIVO = (
    "nombre",
    "tipo",
    "unidades_totales",
    "comision_administrador_pct",
    "moneda",
    "ubicacion",
    "notas",
)


def get_activo() -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM activo LIMIT 1").fetchone()
    finally:
        conn.close()


def crear_o_actualizar_activo(datos: dict) -> int:
    valores = [datos.get(c) for c in CAMPOS_ACTIVO]
    existente = get_activo()
    with db_cursor() as cur:
        if existente:
            asignaciones = ", ".join(f"{c} = ?" for c in CAMPOS_ACTIVO)
            cur.execute(
                f"UPDATE activo SET {asignaciones} WHERE id = ?",
                (*valores, existente["id"]),
            )
            return existente["id"]
        columnas = ", ".join(CAMPOS_ACTIVO)
        marcadores = ", ".join("?" for _ in CAMPOS_ACTIVO)
        cur.execute(
            f"INSERT INTO activo ({columnas}) VALUES ({marcadores})",
            valores,
        )
        return cur.lastrowid


def get_configuracion(activo_id: int) -> dict[str, str]:
    conn = get_connection()
    try:
        filas = conn.execute(
            "SELECT clave, valor FROM configuracion_dominio WHERE activo_id = ?",
            (activo_id,),
        ).fetchall()
        return {f["clave"]: f["valor"] for f in filas}
    finally:
        conn.close()


def set_configuracion(activo_id: int, clave: str, valor) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO configuracion_dominio (activo_id, clave, valor) VALUES (?, ?, ?) "
            "ON CONFLICT(activo_id, clave) DO UPDATE SET valor = excluded.valor",
            (activo_id, clave, str(valor)),
        )


def borrar_configuracion(activo_id: int, clave: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM configuracion_dominio WHERE activo_id = ? AND clave = ?",
            (activo_id, clave),
        )


def _ultimo(tabla: str, activo_id: int) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(
            f"SELECT * FROM {tabla} WHERE activo_id = ? ORDER BY id DESC LIMIT 1",
            (activo_id,),
        ).fetchone()
    finally:
        conn.close()


# --- contrato maestro (se guarda por versiones; vale la última) ---

CAMPOS_CONTRATO = (
    "canon_mensual",
    "fecha_inicio",
    "fecha_vencimiento",
    "vigencia_meses",
    "regla_reajuste",
    "ventana_preaviso_dias",
    "fecha_definicion",
)


def get_contrato_maestro(activo_id: int) -> sqlite3.Row | None:
    return _ultimo("contrato_maestro", activo_id)


def guardar_contrato_maestro(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_CONTRATO))
    marcadores = ", ".join("?" for _ in range(len(CAMPOS_CONTRATO) + 1))
    with db_cursor() as cur:
        cur.execute(
            f"INSERT INTO contrato_maestro ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_CONTRATO)),
        )


# --- política de distribución (por versiones; vale la última) ---

CAMPOS_POLITICA = (
    "porcentaje_libre",
    "porcentaje_reinversion",
    "porcentaje_reserva",
    "tarifa_marginal_actual",
    "calcular_impuesto",
    "fecha_definicion",
)


def get_politica(activo_id: int) -> sqlite3.Row | None:
    return _ultimo("politica_distribucion", activo_id)


def guardar_politica(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_POLITICA))
    marcadores = ", ".join("?" for _ in range(len(CAMPOS_POLITICA) + 1))
    with db_cursor() as cur:
        cur.execute(
            f"INSERT INTO politica_distribucion ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_POLITICA)),
        )


# --- capex (varias filas) ---


def get_capex(activo_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM capex WHERE activo_id = ? ORDER BY fecha DESC, id DESC",
            (activo_id,),
        ).fetchall()
    finally:
        conn.close()


def agregar_capex(activo_id: int, datos: dict) -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO capex (activo_id, concepto, monto, fecha, horizonte_meses) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                activo_id,
                datos.get("concepto"),
                datos.get("monto"),
                datos.get("fecha"),
                datos.get("horizonte_meses"),
            ),
        )
        return cur.lastrowid


def eliminar_capex(activo_id: int, capex_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM capex WHERE id = ? AND activo_id = ?", (capex_id, activo_id)
        )


# --- reporte mensual + unidades ---

CAMPOS_REPORTE = (
    "mes",
    "anio",
    "gastos_fijos",
    "gastos_variables",
    "comision_admin",
    "novedades",
    "fecha_registro",
)


def get_reportes(activo_id: int) -> list[sqlite3.Row]:
    """Cada fila trae los campos del reporte más `ocupacion` e `ingreso_subarriendo`
    derivados de `reporte_unidad`."""
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT r.*,
                   COALESCE(SUM(CASE WHEN u.arrendada = 1 THEN 1 ELSE 0 END), 0) AS ocupacion,
                   COALESCE(SUM(u.ingreso_inquilino), 0) AS ingreso_subarriendo
            FROM reporte_mensual r
            LEFT JOIN reporte_unidad u ON u.reporte_mensual_id = r.id
            WHERE r.activo_id = ?
            GROUP BY r.id
            ORDER BY r.anio DESC, r.mes DESC
            """,
            (activo_id,),
        ).fetchall()
    finally:
        conn.close()


def get_reporte(activo_id: int, anio: int, mes: int):
    """Devuelve (reporte, [unidades]) o (None, []) si el mes no está registrado."""
    conn = get_connection()
    try:
        rep = conn.execute(
            "SELECT * FROM reporte_mensual WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, anio, mes),
        ).fetchone()
        if not rep:
            return None, []
        unidades = conn.execute(
            "SELECT * FROM reporte_unidad WHERE reporte_mensual_id = ? ORDER BY id",
            (rep["id"],),
        ).fetchall()
        return rep, unidades
    finally:
        conn.close()


def guardar_reporte(activo_id: int, datos: dict, unidades: list[dict]) -> int:
    """Reemplaza el reporte del mes si ya existía (corrección). `unidades` es una lista de
    {unidad_label, arrendada (0/1), ingreso_inquilino}."""
    columnas = ", ".join(("activo_id", *CAMPOS_REPORTE))
    marcadores = ", ".join("?" for _ in range(len(CAMPOS_REPORTE) + 1))
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM reporte_mensual WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, datos["anio"], datos["mes"]),
        )
        cur.execute(
            f"INSERT INTO reporte_mensual ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_REPORTE)),
        )
        reporte_id = cur.lastrowid
        for u in unidades:
            cur.execute(
                "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
                "VALUES (?, ?, ?, ?)",
                (reporte_id, u["unidad_label"], u["arrendada"], u["ingreso_inquilino"]),
            )
        return reporte_id


def eliminar_reporte(activo_id: int, anio: int, mes: int) -> None:
    """Las filas de `reporte_unidad` caen solas por ON DELETE CASCADE (schema.sql), porque
    `get_connection()` activa PRAGMA foreign_keys = ON. La asesoría del mes NO cae sola:
    para eso está `eliminar_asesoria`. Y el fondo de reserva hay que reconstruirlo después
    con `dominio.reserva.recalcular_reserva`, porque el saldo es acumulativo."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM reporte_mensual WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, anio, mes),
        )


# --- movimientos del fondo de reserva (derivados; se reconstruyen enteros) ---


def get_reserva_movimientos(activo_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM reserva_movimiento WHERE activo_id = ? ORDER BY anio, mes",
            (activo_id,),
        ).fetchall()
    finally:
        conn.close()


def reemplazar_reserva_movimientos(activo_id: int, movimientos: list[dict]) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM reserva_movimiento WHERE activo_id = ?", (activo_id,))
        for m in movimientos:
            cur.execute(
                "INSERT INTO reserva_movimiento (activo_id, anio, mes, monto, saldo_resultante) "
                "VALUES (?, ?, ?, ?, ?)",
                (activo_id, m["anio"], m["mes"], m["monto"], m["saldo_resultante"]),
            )


# --- recordatorios ---

CAMPOS_RECORDATORIO = (
    "categoria",
    "descripcion",
    "ultima_fecha",
    "frecuencia_meses",
    "fecha_vencimiento_fija",
    "proxima_fecha",
)


def get_recordatorios(activo_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM recordatorios WHERE activo_id = ? ORDER BY proxima_fecha",
            (activo_id,),
        ).fetchall()
    finally:
        conn.close()


def agregar_recordatorio(activo_id: int, datos: dict) -> int:
    columnas = ", ".join(("activo_id", *CAMPOS_RECORDATORIO))
    marcadores = ", ".join("?" for _ in range(len(CAMPOS_RECORDATORIO) + 1))
    with db_cursor() as cur:
        cur.execute(
            f"INSERT INTO recordatorios ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_RECORDATORIO)),
        )
        return cur.lastrowid


def eliminar_recordatorio(activo_id: int, recordatorio_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM recordatorios WHERE id = ? AND activo_id = ?",
            (recordatorio_id, activo_id),
        )


# --- asesoría generada (una por mes; se reemplaza al regenerar) ---

CAMPOS_ASESORIA_DB = (
    "anio",
    "mes",
    "semaforo_resultado",
    "semaforo_ocupacion",
    "resultado_mes",
    "ocupacion_equilibrio",
    "porcentaje_libre_real",
    "brecha_frente_a_meta",
    "capex_recuperado_pct",
    "texto_asesoria",
    "texto_fiscal",
    "fecha_generacion",
)


def get_asesoria(activo_id: int, anio: int, mes: int) -> sqlite3.Row | None:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM asesoria_generada WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, anio, mes),
        ).fetchone()
    finally:
        conn.close()


def guardar_asesoria(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_ASESORIA_DB))
    marcadores = ", ".join("?" for _ in range(len(CAMPOS_ASESORIA_DB) + 1))
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM asesoria_generada WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, datos["anio"], datos["mes"]),
        )
        cur.execute(
            f"INSERT INTO asesoria_generada ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_ASESORIA_DB)),
        )


def eliminar_asesoria(activo_id: int, anio: int, mes: int) -> None:
    """`asesoria_generada` cuelga de `activo_id`, no del reporte, así que no cae sola
    cuando se borra el mes: hay que borrarla aparte."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM asesoria_generada WHERE activo_id = ? AND anio = ? AND mes = ?",
            (activo_id, anio, mes),
        )
