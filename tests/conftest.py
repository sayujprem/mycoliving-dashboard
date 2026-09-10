"""Configuracion de pytest.

Las pruebas corren contra una base PostgreSQL de pruebas. Levantarla en local con:
    scripts/pg_local.sh start

o apuntar a otra con DATABASE_URL_TEST (por ejemplo, un proyecto de Supabase dedicado).

Todo lo de este archivo se ejecuta antes de que cualquier prueba importe `config`, que
lee las variables de entorno una sola vez al importarse.
"""
import os

_URL_TEST = os.environ.get(
    "DATABASE_URL_TEST", "postgresql://postgres@localhost:54329/mycoliving_test"
)

# Salvaguarda: las pruebas hacen drop_all(), que borra todas las tablas. Si por un
# descuido corrieran contra produccion (el .env local puede tener su DATABASE_URL),
# se llevarian por delante los datos de todos los usuarios. Se exige que la base de
# pruebas lo diga en el nombre.
if "test" not in _URL_TEST.rsplit("/", 1)[-1]:
    raise RuntimeError(
        f"La base de pruebas debe llevar 'test' en el nombre. Se recibio: {_URL_TEST}"
    )

# Se fija antes de que load_dotenv lea el .env: python-dotenv no pisa variables que
# ya existen, asi que esta gana sobre cualquier DATABASE_URL del .env.
os.environ["DATABASE_URL"] = _URL_TEST
os.environ["SESSION_SECRET"] = "clave-de-pruebas-no-usar-en-produccion"
os.environ["MYCOLIVING_ENTORNO"] = "pruebas"
os.environ["SMTP_CLAVE"] = ""

# La suite es hermética: no gasta créditos del API. Para ejercitar la corrida real de
# asesoría, correr con:  MYCOLIVING_TEST_REAL_API=1 pytest -k corrida_real
if not os.environ.get("MYCOLIVING_TEST_REAL_API"):
    os.environ["ANTHROPIC_API_KEY"] = ""
