"""Politica de privacidad y terminos: se sirven, son seguros de renderizar y dicen la verdad."""
from pathlib import Path

import pytest

from main import app
from tests.apoyo import ClienteConSesion
from web.legal import DOCUMENTOS, a_html

RAIZ = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("ruta, titulo", [
    ("/privacidad", "Política de privacidad"),
    ("/terminos", "Términos de servicio"),
])
def test_se_pueden_leer_sin_cuenta(ruta, titulo):
    r = ClienteConSesion(app).get(ruta)
    assert r.status_code == 200
    assert titulo in r.text


def test_el_alta_enlaza_a_los_dos_documentos():
    html = ClienteConSesion(app).get("/crear-cuenta").text
    assert 'href="/terminos"' in html and 'href="/privacidad"' in html


def test_el_conversor_escapa_el_html_del_texto():
    _, cuerpo = a_html("Un párrafo con <script>alert(1)</script> dentro.")
    assert "<script>" not in cuerpo
    assert "&lt;script&gt;" in cuerpo


def test_el_conversor_descarta_enlaces_que_no_son_https_ni_propios():
    _, cuerpo = a_html("[clic](javascript:alert(1)) y [bien](https://ejemplo.com) y [interno](/cuenta)")
    assert "javascript:" not in cuerpo
    assert 'href="https://ejemplo.com"' in cuerpo
    assert 'href="/cuenta"' in cuerpo


def test_la_politica_nombra_a_todos_los_que_procesan_datos():
    """Si la plataforma empieza a usar un servicio nuevo, la politica tiene que decirlo."""
    texto = DOCUMENTOS["privacidad"].read_text(encoding="utf-8")
    for encargado in ("Vercel", "Supabase", "Gmail", "Anthropic", "Google"):
        assert encargado in texto, f"la política no menciona a {encargado}"


def test_la_politica_declara_que_las_notas_del_activo_salen_hacia_anthropic():
    """Es el unico texto libre que la asesoria envia al modelo (ver motor/asesor_ia.py)."""
    texto = DOCUMENTOS["privacidad"].read_text(encoding="utf-8")
    assert "notas de contexto" in texto


def test_los_textos_legales_no_tienen_pendientes():
    """Salvaguarda: no se puede publicar una politica con datos por completar.

    Mientras falte algun dato (el correo de privacidad, la fecha de publicacion), esta
    prueba falla a proposito.
    """
    for nombre, ruta in DOCUMENTOS.items():
        texto = ruta.read_text(encoding="utf-8")
        assert "[PENDIENTE" not in texto, f"{ruta.name} todavía tiene datos por completar"
