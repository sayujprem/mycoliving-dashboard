"""Respaldo mensual a Drive. Todo con `ejecutar` falso: la suite no necesita rclone ni red.

El foco de estos tests no es el camino feliz sino que **ningún eslabón falle en silencio**:
un `rclone copy` puede devolver 0 sin haber subido nada.
"""
import os
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from db.init_db import drop_all, init_db
from db.repositorio import get_activo, get_configuracion, set_configuracion
from main import app
from scripts.respaldo import (
    CLAVE_ESTADO,
    nombre_respaldo,
    registrar_estado,
    respaldar,
    snapshot,
    sobrantes,
)
from scripts.seed_coliving import seed

RAIZ_README = __import__("pathlib").Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture
def activo_id():
    drop_all()
    init_db()
    seed()
    return get_activo()["id"]


class _Rclone:
    """Doble de rclone. `fallos` mapea el subcomando a (codigo, salida)."""

    def __init__(self, *, remotos="gdrive:\n", listado="", tamano=None, fallos=None):
        self.remotos = remotos
        self.listado = listado
        self.tamano = tamano
        self.fallos = fallos or {}
        self.llamadas = []

    def __call__(self, args):
        sub = args[1]
        self.llamadas.append(sub)
        if sub in self.fallos:
            return self.fallos[sub]
        if sub == "listremotes":
            return 0, self.remotos
        if sub == "lsd":
            return 0, "  -1 2026-09-07 00:00:00 -1 Seguimiento estratégico\n"
        if sub == "copyto":
            return 0, ""
        if sub == "lsf":
            return 0, self.listado
        if sub == "size":
            return 0, '{"count":1,"bytes":%d}' % (self.tamano if self.tamano is not None else 0)
        if sub == "deletefile":
            return 0, ""
        return 0, ""


def _rclone_feliz(tmp_path, hoy):
    """Doble coherente: el listado y el tamaño coinciden con lo que se acaba de subir."""
    nombre = nombre_respaldo(hoy)

    class _Coherente(_Rclone):
        def __call__(self, args):
            if args[1] == "size":
                from scripts.respaldo import DIR_RESPALDOS

                real = (DIR_RESPALDOS / nombre).stat().st_size
                return 0, '{"count":1,"bytes":%d}' % real
            return super().__call__(args)

    return _Coherente(listado=f"{nombre}\n")


# --- nombres y rotación ---


def test_nombre_del_respaldo_lleva_la_fecha():
    assert nombre_respaldo(date(2026, 9, 5)) == "mycoliving-2026-09-05.db"


def test_rotacion_conserva_las_ultimas_doce():
    nombres = [f"mycoliving-2025-{m:02d}-05.db" for m in range(1, 13)]
    nombres.append("mycoliving-2026-01-05.db")
    viejos = sobrantes(nombres, 12)
    assert viejos == ["mycoliving-2025-01-05.db"]


def test_rotacion_no_borra_nada_si_no_sobran():
    nombres = [f"mycoliving-2025-{m:02d}-05.db" for m in range(1, 6)]
    assert sobrantes(nombres, 12) == []


def test_rotacion_ignora_archivos_ajenos():
    nombres = ["notas.txt", "mycoliving.db", "presupuesto.xlsx",
               *[f"mycoliving-2025-{m:02d}-05.db" for m in range(1, 14)]]
    viejos = sobrantes(nombres, 12)
    assert viejos == ["mycoliving-2025-01-05.db"]
    assert all(v.startswith("mycoliving-2") for v in viejos)


# --- preflight: cada eslabón falla con un mensaje accionable ---


def test_falla_si_rclone_no_esta_instalado(activo_id):
    r = respaldar(rclone="", ejecutar=_Rclone())
    assert r.ok is False
    assert "rclone" in r.error


def test_un_rclone_inexistente_no_revienta_con_traceback(activo_id):
    """Desde launchd nadie va a leer un traceback: tiene que salir el mensaje accionable
    y el código 2. Este caso reventaba de verdad."""
    from scripts.respaldo import main

    r = respaldar(rclone="/no/existe/rclone")
    assert r.ok is False
    assert "No se pudo ejecutar rclone" in r.error

    monkeypatched = os.environ.get("RCLONE_BIN")
    os.environ["RCLONE_BIN"] = "/no/existe/rclone"
    try:
        assert main() == 2  # no lanza excepción
    finally:
        if monkeypatched is None:
            os.environ.pop("RCLONE_BIN", None)
        else:
            os.environ["RCLONE_BIN"] = monkeypatched


def test_falla_si_el_remoto_no_esta_configurado(activo_id):
    r = respaldar(rclone="/fake/rclone", ejecutar=_Rclone(remotos=""))
    assert r.ok is False
    assert "rclone config" in r.error


def test_falla_si_el_token_esta_vencido(activo_id):
    doble = _Rclone(fallos={"lsd": (1, "couldn't fetch token: expired")})
    r = respaldar(rclone="/fake/rclone", ejecutar=doble)
    assert r.ok is False
    assert "token" in r.error


# --- el corazón: no fallar en silencio ---


def test_falla_si_el_archivo_no_aparece_en_el_destino(activo_id):
    """rclone devuelve 0 pero el archivo no está: cuota llena, o el remoto miente."""
    doble = _Rclone(listado="")  # lsf no lo encuentra
    r = respaldar(rclone="/fake/rclone", ejecutar=doble, hoy=date(2026, 9, 5))
    assert r.ok is False
    assert "no quedó en Drive" in r.error


def test_falla_si_el_tamano_no_coincide(activo_id):
    hoy = date(2026, 9, 5)
    doble = _Rclone(listado=f"{nombre_respaldo(hoy)}\n", tamano=17)
    r = respaldar(rclone="/fake/rclone", ejecutar=doble, hoy=hoy)
    assert r.ok is False
    assert "incompleta" in r.error


def test_falla_si_la_subida_devuelve_error(activo_id):
    doble = _Rclone(fallos={"copyto": (1, "quota exceeded")})
    r = respaldar(rclone="/fake/rclone", ejecutar=doble, hoy=date(2026, 9, 5))
    assert r.ok is False
    assert "Falló la subida" in r.error


# --- camino feliz y snapshot ---


def test_respaldo_exitoso_sube_y_verifica(activo_id, tmp_path):
    hoy = date(2026, 9, 5)
    doble = _rclone_feliz(tmp_path, hoy)
    r = respaldar(rclone="/fake/rclone", ejecutar=doble, hoy=hoy)
    assert r.ok is True
    assert r.nombre == "mycoliving-2026-09-05.db"
    # Verificó de verdad: llamó a lsf después de copyto.
    assert doble.llamadas.index("lsf") > doble.llamadas.index("copyto")


def test_el_snapshot_de_sqlite_es_legible(activo_id, tmp_path):
    destino = tmp_path / "copia.db"
    snapshot(destino)
    conn = sqlite3.connect(destino)
    try:
        assert conn.execute("SELECT COUNT(*) FROM activo").fetchone()[0] == 1
    finally:
        conn.close()


# --- el resultado queda donde el usuario mira ---


def test_respaldo_exitoso_registra_el_estado(activo_id, tmp_path):
    hoy = date(2026, 9, 5)
    r = respaldar(rclone="/fake/rclone", ejecutar=_rclone_feliz(tmp_path, hoy), hoy=hoy)
    registrar_estado(r, hoy)
    estado = get_configuracion(activo_id)[CLAVE_ESTADO]
    assert estado.startswith("2026-09-05")
    assert "ok" in estado


def test_respaldo_fallido_tambien_registra_el_estado(activo_id):
    r = respaldar(rclone="", ejecutar=_Rclone())
    registrar_estado(r, date(2026, 9, 5))
    estado = get_configuracion(activo_id)[CLAVE_ESTADO]
    assert "ERROR" in estado


def test_config_muestra_el_ultimo_respaldo(activo_id):
    set_configuracion(activo_id, CLAVE_ESTADO, "2026-09-05 · ok")
    html = TestClient(app).get("/config").text
    assert "Último respaldo" in html
    assert "2026-09-05 · ok" in html


def test_la_clave_de_respaldo_no_la_pisa_el_formulario_de_umbrales(activo_id):
    """respaldo_ultimo no está en CLAVES_CONFIGURACION, así que guardar umbrales
    no puede borrarla."""
    set_configuracion(activo_id, CLAVE_ESTADO, "2026-09-05 · ok")
    c = TestClient(app)
    c.post("/config/umbrales", data={"ocupacion_minima_verde": "4"}, follow_redirects=False)
    assert get_configuracion(activo_id)[CLAVE_ESTADO] == "2026-09-05 · ok"


def test_readme_documenta_el_respaldo():
    readme = RAIZ_README.read_text(encoding="utf-8")
    for pieza in ("rclone", "launchctl", "Seguimiento estratégico", "xattr"):
        assert pieza in readme, f"falta '{pieza}' en el README"
