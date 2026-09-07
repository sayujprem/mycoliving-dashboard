"""Tarea 11: módulo único de conocimiento fiscal colombiano."""
import re
from pathlib import Path

from dominio.fiscal import ADVERTENCIA_ALCANCE, resumen_tabla_241, texto_fiscal

RAIZ = Path(__file__).resolve().parent.parent

TERMINOS_FISCALES = re.compile(
    r"estatuto tributario|art\.? *241|c[eé]dula general|renta no laboral|\buvt\b|"
    r"ley 2277|2277 de 2022|2010 de 2019",
    re.IGNORECASE,
)


def test_conocimiento_fiscal_vive_en_un_solo_archivo():
    ofensores = []
    for ruta in list(RAIZ.glob("*.py")) + [
        p
        for carpeta in ("motor", "dominio", "web", "db")
        for p in (RAIZ / carpeta).rglob("*.py")
    ]:
        if ruta.name == "fiscal.py":
            continue
        if TERMINOS_FISCALES.search(ruta.read_text(encoding="utf-8")):
            ofensores.append(str(ruta.relative_to(RAIZ)))
    assert ofensores == [], f"conocimiento fiscal fuera de dominio/fiscal.py: {ofensores}"


def test_toda_salida_trae_la_advertencia_de_alcance():
    for calcula in (True, False):
        for resultado in (1_000_000, 0, -50_000):
            assert ADVERTENCIA_ALCANCE in texto_fiscal(resultado, 19, calcula)


def test_sin_calcular_impuesto_no_estima_monto():
    t = texto_fiscal(1_000_000, 19, calcular_impuesto=False)
    assert "No se calcula impuesto" in t
    assert "190,000" not in t


def test_con_impuesto_estima_sobre_el_resultado_positivo():
    t = texto_fiscal(1_000_000, 19, calcular_impuesto=True)
    assert "19 %" in t
    assert "190,000" in t  # 1.000.000 * 19%


def test_mes_negativo_no_genera_renta_gravable():
    t = texto_fiscal(-50_000, 28, calcular_impuesto=True)
    assert "no generó renta gravable" in t


def test_resumen_tabla_241_lista_los_tramos():
    r = resumen_tabla_241()
    assert "0 %" in r and "19 %" in r and "39 %" in r
