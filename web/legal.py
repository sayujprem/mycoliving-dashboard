"""Politica de privacidad y terminos de servicio, servidos desde los .md del repositorio.

La fuente es una sola: PRIVACIDAD.md y TERMINOS.md. Lo que se lee en GitHub y lo que se
ve en la plataforma es el mismo texto, sin copias que se desincronicen.

El conversor cubre solo el subconjunto de Markdown que usan esos dos archivos
(encabezados, parrafos, listas, negritas, cursivas, codigo y enlaces). No se agrega una
dependencia para eso. Escapa todo el HTML *antes* de aplicar el formato, asi que ningun
texto del archivo puede inyectar marcado.
"""
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from markupsafe import Markup

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = {"privacidad": RAIZ / "PRIVACIDAD.md", "terminos": RAIZ / "TERMINOS.md"}

_ENLACE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _en_linea(texto: str) -> str:
    t = escape(texto, quote=True)
    t = re.sub(r"`([^`]+)`", r'<code class="mono">\1</code>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)

    def enlace(m: re.Match) -> str:
        url = m.group(2)
        # Solo rutas propias o https: nada de javascript: ni similares.
        if not (url.startswith("/") or url.startswith("https://")):
            return m.group(1)
        externo = ' rel="noopener noreferrer"' if url.startswith("https://") else ""
        return f'<a href="{url}"{externo} style="text-decoration:underline">{m.group(1)}</a>'

    return _ENLACE.sub(enlace, t)


def a_html(markdown: str) -> tuple[str, str]:
    """Devuelve (titulo, cuerpo_html). El titulo es el primer encabezado de nivel 1."""
    titulo = ""
    bloques: list[str] = []
    parrafo: list[str] = []
    lista: list[str] = []

    def cerrar():
        if parrafo:
            bloques.append(f'<p style="margin:0 0 14px">{_en_linea(" ".join(parrafo))}</p>')
            parrafo.clear()
        if lista:
            items = "".join(f'<li style="margin-bottom:6px">{_en_linea(i)}</li>' for i in lista)
            bloques.append(f'<ul style="margin:0 0 14px;padding-left:20px">{items}</ul>')
            lista.clear()

    for linea in markdown.splitlines():
        s = linea.strip()
        if not s:
            cerrar()
        elif s.startswith("# "):
            cerrar()
            titulo = s[2:].strip()
        elif s.startswith("## "):
            cerrar()
            bloques.append(
                f'<h3 style="font-size:17px;margin:26px 0 10px">{_en_linea(s[3:].strip())}</h3>'
            )
        elif s.startswith("- "):
            if parrafo:
                cerrar()
            lista.append(s[2:].strip())
        elif lista and linea.startswith("  "):
            lista[-1] += " " + s  # continuacion del item anterior
        else:
            parrafo.append(s)
    cerrar()
    return titulo, "\n".join(bloques)


@lru_cache(maxsize=None)
def documento(nombre: str) -> tuple[str, Markup]:
    titulo, cuerpo = a_html(DOCUMENTOS[nombre].read_text(encoding="utf-8"))
    # Markup marca el HTML como ya escapado. Es seguro porque a_html escapo cada
    # fragmento de texto antes de envolverlo en etiquetas.
    return titulo, Markup(cuerpo)
