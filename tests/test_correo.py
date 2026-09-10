"""Envio de correo por el SMTP de Gmail, con un servidor simulado: sin red ni credenciales."""
import smtplib

import pytest

import web.correo as correo


class _SMTPFalso:
    """Imita smtplib.SMTP y registra lo que se le pidio."""

    ultimo = None

    def __init__(self, host, puerto, timeout=None, *, fallo=None):
        self.host, self.puerto, self.timeout = host, puerto, timeout
        self.tls = False
        self.login_con = None
        self.enviados = []
        self.fallo = fallo
        _SMTPFalso.ultimo = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = context is not None

    def login(self, usuario, clave):
        if self.fallo == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
        self.login_con = (usuario, clave)

    def send_message(self, mensaje):
        if not self.tls:
            raise AssertionError("se intento enviar sin cifrar la conexion")
        self.enviados.append(mensaje)


@pytest.fixture
def smtp(monkeypatch):
    _SMTPFalso.ultimo = None  # atributo de clase: sin esto arrastra la conexion de otra prueba
    monkeypatch.setattr(correo, "SMTP_CLAVE", "abcdabcdabcdabcd")
    monkeypatch.setattr(correo, "SMTP_USUARIO", "privacidad.mycoliving@gmail.com")
    monkeypatch.setattr(correo.smtplib, "SMTP", _SMTPFalso)
    return _SMTPFalso


def test_envia_por_gmail_con_starttls_y_contrasena_de_aplicacion(smtp):
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok123") is True
    s = smtp.ultimo
    assert (s.host, s.puerto) == ("smtp.gmail.com", 587)
    assert s.tls is True  # STARTTLS con contexto que valida el certificado
    assert s.login_con == ("privacidad.mycoliving@gmail.com", "abcdabcdabcdabcd")
    assert s.timeout is not None  # nunca colgar la funcion esperando al servidor


def test_el_mensaje_lleva_remitente_destinatario_y_enlace(smtp):
    correo.enviar_recuperacion("ana@ejemplo.com", "tok456")
    m = smtp.ultimo.enviados[0]
    assert m["From"] == "MyColiving <privacidad.mycoliving@gmail.com>"
    assert m["To"] == "ana@ejemplo.com"
    assert "/recuperar/tok456" in m.get_content()


def test_un_destinatario_con_salto_de_linea_no_inyecta_cabeceras(smtp):
    malicioso = "ana@ejemplo.com\nBcc: victima@ejemplo.com"
    assert correo.enviar_verificacion(malicioso, "tok") is False
    assert smtp.ultimo is None or smtp.ultimo.enviados == []


def test_credenciales_rechazadas_devuelven_false_sin_reventar(monkeypatch):
    monkeypatch.setattr(correo, "SMTP_CLAVE", "mala")
    monkeypatch.setattr(correo.smtplib, "SMTP", lambda *a, **k: _SMTPFalso(*a, **k, fallo="auth"))
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_sin_red_devuelve_false_sin_reventar(monkeypatch):
    monkeypatch.setattr(correo, "SMTP_CLAVE", "x")

    def sin_red(*a, **k):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(correo.smtplib, "SMTP", sin_red)
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_sin_clave_no_intenta_conectar(monkeypatch):
    monkeypatch.setattr(correo, "SMTP_CLAVE", "")
    monkeypatch.setattr(correo.smtplib, "SMTP", lambda *a, **k: pytest.fail("no debía conectar"))
    assert correo.enviar_verificacion("ana@ejemplo.com", "tok") is False


def test_la_clave_se_acepta_con_los_espacios_con_que_la_muestra_google(monkeypatch):
    monkeypatch.setenv("SMTP_CLAVE", "abcd efgh ijkl mnop")
    import importlib
    import config

    try:
        assert importlib.reload(config).SMTP_CLAVE == "abcdefghijklmnop"
    finally:
        monkeypatch.setenv("SMTP_CLAVE", "")
        importlib.reload(config)
