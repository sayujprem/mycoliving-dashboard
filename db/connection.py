"""Conexion a PostgreSQL.

Dos cosas que no son obvias y conviene tener presentes al tocar este archivo:

1. **Sentencias preparadas apagadas.** La aplicacion se conecta por el transaction
   pooler de Supabase (puerto 6543), que no las soporta. Con el valor por defecto de
   psycopg, la segunda consulta de cada tipo falla.

2. **El aislamiento se arma aca.** Cada transaccion declara de quien son los datos que
   va a tocar, con `SET LOCAL ROLE` + `SET LOCAL app.usuario_id`. El id no se lo pasa
   nadie a mano: sale de una variable de contexto que fija la capa de sesion. Asi el
   repositorio no cambia de forma y no hay manera de olvidarse de filtrar.

`SET LOCAL` dura exactamente lo que dura la transaccion, que es justo lo que el
transaction pooler garantiza que es nuestro. Al terminar, la conexion vuelve limpia
al pool.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.numeric import FloatLoader

from config import DATABASE_URL, DB_ROL_APP

# Las columnas de dinero son NUMERIC, que es exacto y no acumula error de redondeo al
# guardar. psycopg las devolveria como Decimal, pero dominio/ y motor/ calculan en
# float y mezclar los dos tipos revienta en la primera suma. Se convierten aca, en la
# frontera: la base sigue siendo exacta y la logica de negocio no cambia.
psycopg.adapters.register_loader("numeric", FloatLoader)

# Dueno de la peticion en curso. La fija web/auth.py al resolver la sesion y la lee
# db_cursor() sin que el codigo de dominio se entere.
USUARIO_ACTUAL: ContextVar[int | None] = ContextVar("usuario_actual", default=None)


def fijar_usuario(usuario_id: int | None) -> None:
    """Declara de quien son los datos de esta peticion. Solo la capa de sesion llama aca."""
    USUARIO_ACTUAL.set(usuario_id)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        # Obligatorio con el transaction pooler.
        prepare_threshold=None,
        autocommit=False,
    )


@contextmanager
def db_cursor(privilegiado: bool = False) -> Iterator[psycopg.Cursor]:
    """Abre una transaccion acotada al usuario en contexto.

    `privilegiado=True` la abre sin RLS. Es para las operaciones que ocurren antes de
    que exista una identidad (login, alta de cuenta, verificacion de correo) y para
    los scripts de migracion y respaldo. Fuera de web/auth.py y scripts/, nada deberia
    necesitarlo: si sientes la tentacion de usarlo en una ruta, el problema esta en
    otra parte.
    """
    usuario_id = USUARIO_ACTUAL.get()
    conn = get_connection()
    try:
        with conn:  # commit al salir sin error, rollback si hay excepcion
            with conn.cursor() as cur:
                if not privilegiado:
                    # Sin rol acotado, el rol de conexion de Supabase ignora las
                    # politicas y RLS no protegeria nada.
                    cur.execute(f"SET LOCAL ROLE {DB_ROL_APP}")
                    cur.execute(
                        "SELECT set_config('app.usuario_id', %s, true)",
                        ("" if usuario_id is None else str(usuario_id),),
                    )
                yield cur
    finally:
        conn.close()
