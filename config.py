"""Configuracion del proyecto, leida de variables de entorno.

No hay valores de negocio aca. Los datos del activo (numero de unidades, comision,
umbrales) viven en la base de datos, no en el codigo.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Carga variables desde .env si existe (no sobrescribe las ya presentes en el entorno).
load_dotenv(BASE_DIR / ".env")

# Ruta del archivo SQLite. Se puede sobreescribir con MYCOLIVING_DB_PATH.
DB_PATH = Path(os.environ.get("MYCOLIVING_DB_PATH") or (BASE_DIR / "mycoliving.db"))

# Clave del API de Anthropic. Solo se usa para el informe de asesoria (tareas 12-13).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Requerido solo si la API key esta ligada a una identidad/organizacion con workspaces.
ANTHROPIC_WORKSPACE_ID = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")

# Modelo para el informe de asesoria. Se puede cambiar sin tocar codigo.
MODELO_ASESORIA = os.environ.get("MYCOLIVING_MODELO", "claude-opus-5")
