"""El script que obtiene el permiso de Gmail pide lo justo y lo pide de forma segura."""
import base64
import hashlib
import json
import urllib.parse

import pytest

from scripts.autorizar_gmail import ALCANCE, leer_cliente, pkce, url_autorizacion


def test_el_reto_pkce_es_el_sha256_del_verificador():
    verificador, reto = pkce()
    esperado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    assert reto == esperado
    assert 43 <= len(verificador) <= 128  # lo que exige el estándar PKCE


def test_la_url_pide_solo_enviar_y_un_permiso_de_larga_duracion():
    url = url_autorizacion("cid", "http://127.0.0.1:5000", "reto", "estado")
    q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
    assert q["scope"] == ALCANCE == "https://www.googleapis.com/auth/gmail.send"
    assert q["access_type"] == "offline" and q["prompt"] == "consent"
    assert q["code_challenge_method"] == "S256" and q["code_challenge"] == "reto"
    assert q["state"] == "estado"
    assert q["redirect_uri"].startswith("http://127.0.0.1:")


def test_acepta_el_json_de_un_cliente_de_escritorio(tmp_path):
    ruta = tmp_path / "cliente.json"
    ruta.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}))
    assert leer_cliente(ruta)["client_id"] == "cid"


def test_rechaza_un_cliente_que_no_es_de_escritorio(tmp_path):
    ruta = tmp_path / "cliente.json"
    ruta.write_text(json.dumps({"web": {"client_id": "cid", "client_secret": "csec"}}))
    with pytest.raises(SystemExit, match="App de escritorio"):
        leer_cliente(ruta)
