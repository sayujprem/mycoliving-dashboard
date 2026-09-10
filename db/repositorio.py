"""Acceso a datos. Capa de persistencia: ni motor ni dominio, solo lectura/escritura.

Cada cuenta tiene un activo. `get_activo(usuario_id)` es la unica puerta de entrada a
la tabla `activo` y siempre exige saber de quien son los datos; el resto de funciones
trabaja con el `activo_id` que sale de ahi. Ninguna acepta un identificador que venga
del cliente.

Todas las consultas pasan por `db_cursor()`, que ademas aplica las politicas de
aislamiento de la base. Una lectura que abra su propia conexion se saltaria esa capa.
"""
from db.connection import db_cursor

CAMPOS_ACTIVO = (
    "nombre",
    "tipo",
    "unidades_totales",
    "comision_administrador_pct",
    "moneda",
    "ubicacion",
    "notas",
)


def get_activo(usuario_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM activo WHERE usuario_id = %s", (usuario_id,))
        return cur.fetchone()


def crear_o_actualizar_activo(usuario_id: int, datos: dict) -> int:
    """Crea el activo de la cuenta, o actualiza el que ya tenga.

    El UNIQUE sobre usuario_id impide que una cuenta acumule activos, y el WHERE
    impide que el UPDATE toque el de otra.
    """
    valores = [datos.get(c) for c in CAMPOS_ACTIVO]
    with db_cursor() as cur:
        cur.execute("SELECT id FROM activo WHERE usuario_id = %s", (usuario_id,))
        existente = cur.fetchone()
        if existente:
            asignaciones = ", ".join(f"{c} = %s" for c in CAMPOS_ACTIVO)
            cur.execute(
                f"UPDATE activo SET {asignaciones} WHERE id = %s AND usuario_id = %s",
                (*valores, existente["id"], usuario_id),
            )
            return existente["id"]
        columnas = ", ".join(("usuario_id", *CAMPOS_ACTIVO))
        marcadores = ", ".join("%s" for _ in range(len(CAMPOS_ACTIVO) + 1))
        cur.execute(
            f"INSERT INTO activo ({columnas}) VALUES ({marcadores}) RETURNING id",
            (usuario_id, *valores),
        )
        return cur.fetchone()["id"]


def get_activo_por_id(activo_id: int) -> dict | None:
    """Lee el activo a partir de su id, para el codigo de dominio que ya lo recibe.

    No hace falta pasar el usuario: la politica de aislamiento de la base solo deja ver
    la fila si pertenece al dueno de la peticion en curso.
    """
    with db_cursor() as cur:
        cur.execute("SELECT * FROM activo WHERE id = %s", (activo_id,))
        return cur.fetchone()


def eliminar_activo(usuario_id: int) -> None:
    """Borra el activo y, en cascada, todo su historico."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM activo WHERE usuario_id = %s", (usuario_id,))


def get_configuracion(activo_id: int) -> dict[str, str]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT clave, valor FROM configuracion_dominio WHERE activo_id = %s",
            (activo_id,),
        )
        return {f["clave"]: f["valor"] for f in cur.fetchall()}


def set_configuracion(activo_id: int, clave: str, valor) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO configuracion_dominio (activo_id, clave, valor) VALUES (%s, %s, %s) "
            "ON CONFLICT (activo_id, clave) DO UPDATE SET valor = excluded.valor",
            (activo_id, clave, str(valor)),
        )


def borrar_configuracion(activo_id: int, clave: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM configuracion_dominio WHERE activo_id = %s AND clave = %s",
            (activo_id, clave),
        )


# Las tablas versionadas guardan una fila por cambio y vale la ultima. El nombre de
# tabla sale de las constantes de este modulo, nunca de entrada del usuario.
def _ultimo(tabla: str, activo_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute(
            f"SELECT * FROM {tabla} WHERE activo_id = %s ORDER BY id DESC LIMIT 1",
            (activo_id,),
        )
        return cur.fetchone()


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


def get_contrato_maestro(activo_id: int) -> dict | None:
    return _ultimo("contrato_maestro", activo_id)


def guardar_contrato_maestro(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_CONTRATO))
    marcadores = ", ".join("%s" for _ in range(len(CAMPOS_CONTRATO) + 1))
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


def get_politica(activo_id: int) -> dict | None:
    return _ultimo("politica_distribucion", activo_id)


def guardar_politica(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_POLITICA))
    marcadores = ", ".join("%s" for _ in range(len(CAMPOS_POLITICA) + 1))
    with db_cursor() as cur:
        cur.execute(
            f"INSERT INTO politica_distribucion ({columnas}) VALUES ({marcadores})",
            (activo_id, *(datos.get(c) for c in CAMPOS_POLITICA)),
        )


# --- capex (varias filas) ---


def get_capex(activo_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM capex WHERE activo_id = %s ORDER BY fecha DESC, id DESC",
            (activo_id,),
        )
        return cur.fetchall()


def agregar_capex(activo_id: int, datos: dict) -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO capex (activo_id, concepto, monto, fecha, horizonte_meses) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (
                activo_id,
                datos.get("concepto"),
                datos.get("monto"),
                datos.get("fecha"),
                datos.get("horizonte_meses"),
            ),
        )
        return cur.fetchone()["id"]


def eliminar_capex(activo_id: int, capex_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM capex WHERE id = %s AND activo_id = %s", (capex_id, activo_id)
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


def get_reportes(activo_id: int) -> list[dict]:
    """Cada fila trae los campos del reporte más `ocupacion` e `ingreso_subarriendo`
    derivados de `reporte_unidad`."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.*,
                   COALESCE(SUM(CASE WHEN u.arrendada THEN 1 ELSE 0 END), 0) AS ocupacion,
                   COALESCE(SUM(u.ingreso_inquilino), 0) AS ingreso_subarriendo
            FROM reporte_mensual r
            LEFT JOIN reporte_unidad u ON u.reporte_mensual_id = r.id
            WHERE r.activo_id = %s
            GROUP BY r.id
            ORDER BY r.anio DESC, r.mes DESC
            """,
            (activo_id,),
        )
        return cur.fetchall()


def get_reporte(activo_id: int, anio: int, mes: int):
    """Devuelve (reporte, [unidades]) o (None, []) si el mes no está registrado."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM reporte_mensual WHERE activo_id = %s AND anio = %s AND mes = %s",
            (activo_id, anio, mes),
        )
        rep = cur.fetchone()
        if not rep:
            return None, []
        cur.execute(
            "SELECT * FROM reporte_unidad WHERE reporte_mensual_id = %s ORDER BY id",
            (rep["id"],),
        )
        return rep, cur.fetchall()


def guardar_reporte(activo_id: int, datos: dict, unidades: list[dict]) -> int:
    """Reemplaza el reporte del mes si ya existía (corrección). `unidades` es una lista de
    {unidad_label, arrendada (bool), ingreso_inquilino}."""
    columnas = ", ".join(("activo_id", *CAMPOS_REPORTE))
    marcadores = ", ".join("%s" for _ in range(len(CAMPOS_REPORTE) + 1))
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM reporte_mensual WHERE activo_id = %s AND anio = %s AND mes = %s",
            (activo_id, datos["anio"], datos["mes"]),
        )
        cur.execute(
            f"INSERT INTO reporte_mensual ({columnas}) VALUES ({marcadores}) RETURNING id",
            (activo_id, *(datos.get(c) for c in CAMPOS_REPORTE)),
        )
        reporte_id = cur.fetchone()["id"]
        for u in unidades:
            cur.execute(
                "INSERT INTO reporte_unidad (reporte_mensual_id, unidad_label, arrendada, ingreso_inquilino) "
                "VALUES (%s, %s, %s, %s)",
                (reporte_id, u["unidad_label"], bool(u["arrendada"]), u["ingreso_inquilino"]),
            )
        return reporte_id


def eliminar_reporte(activo_id: int, anio: int, mes: int) -> None:
    """Las filas de `reporte_unidad` caen solas por ON DELETE CASCADE (schema.sql). La
    asesoría del mes NO cae sola: para eso está `eliminar_asesoria`. Y el fondo de
    reserva hay que reconstruirlo después con `dominio.reserva.recalcular_reserva`,
    porque el saldo es acumulativo."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM reporte_mensual WHERE activo_id = %s AND anio = %s AND mes = %s",
            (activo_id, anio, mes),
        )


# --- movimientos del fondo de reserva (derivados; se reconstruyen enteros) ---


def get_reserva_movimientos(activo_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM reserva_movimiento WHERE activo_id = %s ORDER BY anio, mes",
            (activo_id,),
        )
        return cur.fetchall()


def reemplazar_reserva_movimientos(activo_id: int, movimientos: list[dict]) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM reserva_movimiento WHERE activo_id = %s", (activo_id,))
        for m in movimientos:
            cur.execute(
                "INSERT INTO reserva_movimiento (activo_id, anio, mes, monto, saldo_resultante) "
                "VALUES (%s, %s, %s, %s, %s)",
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


def get_recordatorios(activo_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM recordatorios WHERE activo_id = %s ORDER BY proxima_fecha",
            (activo_id,),
        )
        return cur.fetchall()


def agregar_recordatorio(activo_id: int, datos: dict) -> int:
    columnas = ", ".join(("activo_id", *CAMPOS_RECORDATORIO))
    marcadores = ", ".join("%s" for _ in range(len(CAMPOS_RECORDATORIO) + 1))
    with db_cursor() as cur:
        cur.execute(
            f"INSERT INTO recordatorios ({columnas}) VALUES ({marcadores}) RETURNING id",
            (activo_id, *(datos.get(c) for c in CAMPOS_RECORDATORIO)),
        )
        return cur.fetchone()["id"]


def eliminar_recordatorio(activo_id: int, recordatorio_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM recordatorios WHERE id = %s AND activo_id = %s",
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


def get_asesoria(activo_id: int, anio: int, mes: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM asesoria_generada WHERE activo_id = %s AND anio = %s AND mes = %s",
            (activo_id, anio, mes),
        )
        return cur.fetchone()


def guardar_asesoria(activo_id: int, datos: dict) -> None:
    columnas = ", ".join(("activo_id", *CAMPOS_ASESORIA_DB))
    marcadores = ", ".join("%s" for _ in range(len(CAMPOS_ASESORIA_DB) + 1))
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM asesoria_generada WHERE activo_id = %s AND anio = %s AND mes = %s",
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
            "DELETE FROM asesoria_generada WHERE activo_id = %s AND anio = %s AND mes = %s",
            (activo_id, anio, mes),
        )
