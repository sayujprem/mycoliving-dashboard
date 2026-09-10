"""Respaldo mensual a Drive. Todo con `ejecutar` falso: la suite no necesita pg_dump,
gpg, rclone ni red.

El foco no es el camino feliz sino que **ningún eslabón falle en silencio** (un
`rclone copy` puede devolver 0 sin haber subido nada) y que **nunca se suba una copia
sin cifrar**.
"""
from datetime import date
from pathlib import Path

from scripts.respaldo import main, nombre_respaldo, respaldar, sobrantes

RAIZ = Path(__file__).resolve().parent.parent
HOY = date(2026, 9, 5)
BINARIOS = {"pg_dump": "/fake/pg_dump", "gpg": "/fake/gpg", "rclone": "/fake/rclone"}
URL = "postgresql://postgres.ref:clave@pooler.supabase.com:5432/postgres"


class _Doble:
    """Doble de pg_dump, gpg y rclone. `fallos` mapea un paso a (codigo, salida).

    Los pasos se nombran por binario y, para rclone, por subcomando: "pg_dump", "gpg",
    "listremotes", "lsd", "copyto", "lsf", "size", "deletefile".
    """

    def __init__(self, *, remotos="respaldos:\n", listado=None, tamano=None, fallos=None,
                 volcado=b"PGDMP-volcado-falso"):
        self.remotos = remotos
        self.listado = listado
        self.tamano = tamano
        self.fallos = fallos or {}
        self.volcado = volcado
        self.llamadas: list[str] = []
        self.entradas: dict[str, str | None] = {}
        self.argumentos: dict[str, list[str]] = {}
        self._tamano_cifrado = None

    def __call__(self, args, entrada=None):
        binario = Path(args[0]).name
        paso = args[1] if binario == "rclone" else binario
        self.llamadas.append(paso)
        self.entradas[paso] = entrada
        self.argumentos[paso] = args
        if paso in self.fallos:
            return self.fallos[paso]

        if paso == "pg_dump":
            destino = next(a.split("=", 1)[1] for a in args if a.startswith("--file="))
            Path(destino).write_bytes(self.volcado)
            return 0, ""
        if paso == "gpg":
            salida = Path(args[args.index("--output") + 1])
            origen = Path(args[-1])
            salida.write_bytes(b"GPG" + origen.read_bytes())
            self._tamano_cifrado = salida.stat().st_size
            return 0, ""
        if paso == "listremotes":
            return 0, self.remotos
        if paso == "lsf":
            listado = self.listado if self.listado is not None else nombre_respaldo(HOY) + "\n"
            return 0, listado
        if paso == "size":
            bytes_ = self.tamano if self.tamano is not None else self._tamano_cifrado
            return 0, '{"count":1,"bytes":%d}' % bytes_
        return 0, ""


def _respaldar(doble, **kw):
    base = dict(url=URL, clave="frase-secreta", hoy=HOY, ejecutar=doble, binarios=BINARIOS)
    return respaldar(**{**base, **kw})


# --- nombres y rotación ---


def test_nombre_del_respaldo_lleva_la_fecha_y_la_marca_de_cifrado():
    assert nombre_respaldo(date(2026, 9, 5)) == "mycoliving-2026-09-05.dump.gpg"


def test_rotacion_conserva_las_ultimas_doce():
    nombres = [f"mycoliving-2025-{m:02d}-05.dump.gpg" for m in range(1, 13)]
    nombres.append("mycoliving-2026-01-05.dump.gpg")
    assert sobrantes(nombres, 12) == ["mycoliving-2025-01-05.dump.gpg"]


def test_rotacion_no_borra_nada_si_no_sobran():
    nombres = [f"mycoliving-2025-{m:02d}-05.dump.gpg" for m in range(1, 6)]
    assert sobrantes(nombres, 12) == []


def test_rotacion_ignora_archivos_ajenos_y_respaldos_viejos_de_sqlite():
    nombres = ["notas.txt", "mycoliving-2024-01-05.db", "presupuesto.xlsx",
               *[f"mycoliving-2025-{m:02d}-05.dump.gpg" for m in range(1, 14)]]
    assert sobrantes(nombres, 12) == ["mycoliving-2025-01-05.dump.gpg"]


# --- nunca en claro ---


def test_sin_clave_de_cifrado_no_se_respalda_nada():
    doble = _Doble()
    r = _respaldar(doble, clave="")
    assert r.ok is False
    assert "RESPALDO_CLAVE" in r.error
    assert doble.llamadas == []  # ni siquiera se volcó la base


def test_si_gpg_falla_no_se_sube_nada():
    doble = _Doble(fallos={"gpg": (2, "gpg: error")})
    r = _respaldar(doble)
    assert r.ok is False
    assert "cifrar" in r.error
    assert "copyto" not in doble.llamadas


def test_la_frase_de_cifrado_va_por_stdin_y_no_en_los_argumentos():
    """Los argumentos de un proceso los puede leer cualquier otro proceso de la máquina."""
    doble = _Doble()
    _respaldar(doble)
    assert doble.entradas["gpg"] == "frase-secreta"
    assert "frase-secreta" not in " ".join(doble.argumentos["gpg"])


def test_lo_que_se_sube_es_el_archivo_cifrado():
    doble = _Doble()
    _respaldar(doble)
    origen = doble.argumentos["copyto"][2]
    assert origen.endswith(".dump.gpg")


def test_el_volcado_solo_toma_el_esquema_de_la_aplicacion():
    doble = _Doble()
    _respaldar(doble)
    assert "--schema=public" in doble.argumentos["pg_dump"]


def test_un_error_de_pg_dump_no_expone_la_cadena_de_conexion():
    doble = _Doble(fallos={"pg_dump": (1, f"connection to {URL} failed")})
    r = _respaldar(doble)
    assert r.ok is False
    assert "clave" not in r.error and "pooler" not in r.error


# --- preflight: cada eslabón falla con un mensaje accionable ---


def test_falla_si_falta_la_url():
    r = _respaldar(_Doble(), url="")
    assert r.ok is False
    assert "DATABASE_URL_RESPALDO" in r.error


def test_falla_si_falta_un_binario():
    r = _respaldar(_Doble(), binarios={**BINARIOS, "pg_dump": None})
    assert r.ok is False
    assert "pg_dump" in r.error


def test_un_rclone_inexistente_no_revienta_con_traceback(monkeypatch):
    """En GitHub Actions nadie lee un traceback: tiene que salir el mensaje y el código 2."""
    r = respaldar(url=URL, clave="x", binarios={**BINARIOS, "rclone": "/no/existe/rclone"})
    assert r.ok is False
    assert "No se pudo ejecutar rclone" in r.error

    monkeypatch.setenv("DATABASE_URL_RESPALDO", URL)
    monkeypatch.setenv("RESPALDO_CLAVE", "x")
    monkeypatch.setenv("RCLONE_BIN", "/no/existe/rclone")
    monkeypatch.setenv("PG_DUMP_BIN", "/no/existe/pg_dump")
    monkeypatch.setenv("GPG_BIN", "/no/existe/gpg")
    assert main() == 2  # no lanza excepción


def test_falla_si_el_remoto_no_esta_configurado():
    r = _respaldar(_Doble(remotos=""))
    assert r.ok is False
    assert "no está configurado" in r.error


def test_falla_si_el_token_esta_vencido():
    r = _respaldar(_Doble(fallos={"lsd": (1, "couldn't fetch token: expired")}))
    assert r.ok is False
    assert "token" in r.error


# --- el corazón: no fallar en silencio ---


def test_falla_si_el_archivo_no_aparece_en_el_destino():
    """rclone devuelve 0 pero el archivo no está: cuota llena, o el remoto miente."""
    r = _respaldar(_Doble(listado=""))
    assert r.ok is False
    assert "no quedó en Drive" in r.error


def test_falla_si_el_tamano_no_coincide():
    r = _respaldar(_Doble(tamano=17))
    assert r.ok is False
    assert "incompleta" in r.error


def test_falla_si_la_subida_devuelve_error():
    r = _respaldar(_Doble(fallos={"copyto": (1, "quota exceeded")}))
    assert r.ok is False
    assert "Falló la subida" in r.error


def test_respaldo_exitoso_sube_y_verifica():
    doble = _Doble()
    r = _respaldar(doble)
    assert r.ok is True
    assert r.nombre == "mycoliving-2026-09-05.dump.gpg"
    # Verificó de verdad: listó el destino después de subir.
    assert doble.llamadas.index("lsf") > doble.llamadas.index("copyto")
    # Y el orden de la cadena es volcar, cifrar, subir.
    assert doble.llamadas.index("pg_dump") < doble.llamadas.index("gpg") < doble.llamadas.index("copyto")


def test_no_quedan_copias_locales_tras_el_respaldo(tmp_path):
    _respaldar(_Doble(), directorio=tmp_path)
    assert list(tmp_path.iterdir()) == []


# --- documentación y automatización ---


def test_hay_un_workflow_mensual_de_respaldo():
    flujo = (RAIZ / ".github" / "workflows" / "respaldo.yml").read_text(encoding="utf-8")
    for pieza in ("schedule", "cron", "scripts.respaldo", "RESPALDO_CLAVE", "DATABASE_URL_RESPALDO"):
        assert pieza in flujo, f"falta '{pieza}' en el workflow"


def test_readme_documenta_el_respaldo():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    for pieza in ("RESPALDO_CLAVE", "pg_restore", "gpg --decrypt", "rclone"):
        assert pieza in readme, f"falta '{pieza}' en el README"


def test_el_token_se_valida_en_la_raiz_aunque_la_carpeta_aun_no_exista():
    """En la primera corrida la carpeta de destino no existe: la crea la subida. Si el
    lsd apuntara a ella, el respaldo fallaria como si el token estuviera vencido."""
    doble = _Doble()
    _respaldar(doble, remoto="respaldos:mycoliving/")
    assert doble.argumentos["lsd"][2] == "respaldos:"


def test_el_destino_sin_barra_final_se_normaliza():
    doble = _Doble()
    _respaldar(doble, remoto="respaldos:mycoliving")
    assert doble.argumentos["copyto"][3] == "respaldos:mycoliving/mycoliving-2026-09-05.dump.gpg"
