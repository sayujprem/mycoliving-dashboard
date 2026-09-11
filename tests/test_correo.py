"""Envio de correo por la API de Gmail, contra un Google simulado: sin red ni permisos reales."""
import base64
import email
import io
import json
import urllib.error

import pytest

import web.correo as correo

CRED = json.dumps({"client_id": "cid", "client_secret": "csec", "refresh_token": "rtok"})


class _Google:
    """Imita los dos extremos que usa la aplicacion: el de tokens y el de envio."""

    def __init__(self, *, token_error=None, envio_errores=()):
        self.token_error = token_error
        self.envio_errores = list(envio_errores)
        self.pedidos_token = 0
        self.envios: list[dict] = []

    def __call__(self, peticion, timeout=None):
        assert timeout, "toda llamada debe llevar timeout"
        url = peticion.full_url
        if url == correo.TOKEN_URL:
            self.pedidos_token += 1
            if self.token_error:
                codigo, cuerpo = self.token_error
                raise urllib.error.HTTPError(url, codigo, "err", {}, io.BytesIO(cuerpo.encode()))
            return io.BytesIO(json.dumps({"access_token": f"at{self.pedidos_token}", "expires_in": 3600}).encode())
        if url == correo.ENVIO_URL:
            if self.envio_errores:
                codigo = self.envio_errores.pop(0)
                raise urllib.error.HTTPError(url, codigo, "err", {}, io.BytesIO(b'{"error":"x"}'))
            self.envios.append({
                "auth": peticion.get_header("Authorization"),
                "cuerpo": json.loads(peticion.data),
            })
            return io.BytesIO(b'{"id":"msg1"}')
        raise AssertionError(f"URL inesperada: {url}")


@pytest.fixture
def google(monkeypatch):
    falso = _Google()
    monkeypatch.setattr(correo, "GMAIL_OAUTH", CRED)
    monkeypatch.setattr(correo, "CORREO_REMITENTE", "privacidad.mycoliving@gmail.com")
    monkeypatch.setattr(correo, "_abrir", falso)
    monkeypatch.setattr(correo, "_cache", {"token": None, "vence": 0.0})
    return falso


def _mensaje(envio) -> email.message.Message:
    return email.message_from_bytes(base64.urlsafe_b64decode(envio["cuerpo"]["raw"]))


def test_envia_por_la_api_con_un_token_de_acceso(google):
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok123") is True
    assert google.pedidos_token == 1
    assert google.envios[0]["auth"] == "Bearer at1"


def test_el_mensaje_lleva_remitente_destinatario_y_enlace(google):
    correo.enviar_recuperacion("ana@ejemplo.com", "tok456")
    m = _mensaje(google.envios[0])
    assert m["From"] == "MyColiving <privacidad.mycoliving@gmail.com>"
    assert m["To"] == "ana@ejemplo.com"
    assert "/recuperar/tok456" in m.get_payload(decode=True).decode()


def test_la_credencial_se_reutiliza_mientras_no_vence(google):
    correo.enviar_verificacion("a@ejemplo.com", "t1")
    correo.enviar_verificacion("b@ejemplo.com", "t2")
    assert google.pedidos_token == 1
    assert len(google.envios) == 2


def test_un_401_renueva_la_credencial_y_reintenta_una_vez(google):
    google.envio_errores = [401]
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is True
    assert google.pedidos_token == 2
    assert google.envios[0]["auth"] == "Bearer at2"


def test_dos_401_seguidos_se_rinden_sin_reventar(google):
    google.envio_errores = [401, 401]
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_permiso_revocado_devuelve_false_y_dice_como_arreglarlo(google, caplog):
    google.token_error = (400, '{"error":"invalid_grant"}')
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False
    assert "autorizar_gmail" in caplog.text


def test_un_error_de_la_api_devuelve_false(google):
    google.envio_errores = [403]
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_sin_red_devuelve_false_sin_reventar(google, monkeypatch):
    def sin_red(*a, **k):
        raise urllib.error.URLError("Network is unreachable")

    monkeypatch.setattr(correo, "_abrir", sin_red)
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_un_destinatario_con_salto_de_linea_no_inyecta_cabeceras(google):
    malicioso = "ana@ejemplo.com\nBcc: victima@ejemplo.com"
    assert correo.enviar_verificacion(malicioso, "tok") is False
    assert google.envios == [] and google.pedidos_token == 0


def test_sin_permiso_no_intenta_conectar(monkeypatch):
    monkeypatch.setattr(correo, "GMAIL_OAUTH", "")
    monkeypatch.setattr(correo, "_abrir", lambda *a, **k: pytest.fail("no debía conectar"))
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


@pytest.mark.parametrize("valor", ["no es json", '{"client_id":"x"}'])
def test_un_permiso_mal_formado_no_intenta_conectar(monkeypatch, valor):
    monkeypatch.setattr(correo, "GMAIL_OAUTH", valor)
    monkeypatch.setattr(correo, "_abrir", lambda *a, **k: pytest.fail("no debía conectar"))
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False
