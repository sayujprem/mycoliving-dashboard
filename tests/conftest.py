"""Configuracion de pytest: usa una base de datos SQLite temporal para toda la sesion.

Se define MYCOLIVING_DB_PATH antes de que cualquier test importe `config`, para que
ninguna prueba toque la base de datos real del proyecto.
"""
import os
import tempfile
from pathlib import Path

_TMP_DIR = tempfile.mkdtemp(prefix="mycoliving-test-")
os.environ["MYCOLIVING_DB_PATH"] = str(Path(_TMP_DIR) / "test.db")

# La suite es hermética: no gasta créditos del API. Para ejercitar la corrida real de
# asesoría, correr con:  MYCOLIVING_TEST_REAL_API=1 pytest -k corrida_real
if not os.environ.get("MYCOLIVING_TEST_REAL_API"):
    os.environ["ANTHROPIC_API_KEY"] = ""
