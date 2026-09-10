"""Cuentas: alta, verificacion, acceso, recuperacion, perfil, administracion y CSRF."""
import re

import pytest

import web.correo as correo
from db.init_db import drop_all, init_db
from db.usuarios import get_usuario_por_email, set_asesoria_habilitada
from main import app
from tests.apoyo import PASSWORD_PRUEBA, ClienteConSesion, nuevo_cliente


@pytest.fixture
def buzon(monkeypatch):
    """Captura los correos en vez de enviarlos."""
    drop_all()
    init_db()
    enviados: list[dict] = []
    monkeypatch.setattr(
        correo, "_enviar", lambda destino, asunto, cuerpo: enviados.append(
            {"destino": destino, "asunto": asunto, "cuerpo": cuerpo}) or True
    )
    return enviados


def _anonimo():
    return ClienteConSesion(app)


def _alta(cliente, email="ana@ejemplo.com", password="clave-muy-segura", **extra):
    datos = {"email": email, "password": password, "confirmacion": password, "acepta": "1", **extra}
    return cliente.post("/crear-cuenta", data=datos)


def _token(correo_enviado, ruta):
    return re.search(rf"/{ruta}/(\S+)", correo_enviado["cuerpo"]).group(1)


# --- alta y verificacion ---


def test_alta_envia_verificacion_y_no_inicia_sesion(buzon):
    c = _anonimo()
    r = _alta(c)
    assert "Revisa tu correo" in r.text
    assert len(buzon) == 1 and buzon[0]["destino"] == "ana@ejemplo.com"
    assert c.get("/", follow_redirects=False).headers["location"] == "/entrar"


def test_alta_normaliza_el_correo(buzon):
    _alta(_anonimo(), email="  Ana@Ejemplo.COM ")
    assert get_usuario_por_email("ana@ejemplo.com") is not None


@pytest.mark.parametrize("password, confirmacion, mensaje", [
    ("corta", "corta", "al menos 10"),
    ("x" * 129, "x" * 129, "no puede pasar de"),
    ("clave-muy-segura", "otra-clave-larga", "no coinciden"),
])
def test_alta_valida_la_contrasena(buzon, password, confirmacion, mensaje):
    r = _anonimo().post("/crear-cuenta", data={"email": "a@b.co", "password": password,
                        "confirmacion": confirmacion, "acepta": "1"})
    assert r.status_code == 400 and mensaje in r.text
    assert buzon == []


def test_alta_exige_aceptar_los_terminos(buzon):
    r = _anonimo().post("/crear-cuenta", data={"email": "a@b.co", "password": "clave-muy-segura",
                        "confirmacion": "clave-muy-segura"})
    assert r.status_code == 400 and "términos" in r.text


def test_alta_repetida_no_revela_que_la_cuenta_existe(buzon):
    primera = _alta(_anonimo())
    segunda = _alta(_anonimo(), password="otra-clave-distinta")
    assert "Revisa tu correo" in primera.text and "Revisa tu correo" in segunda.text
    assert len(buzon) == 1  # la segunda no crea nada ni avisa


def test_abrir_el_enlace_no_verifica_hasta_pulsar_el_boton(buzon):
    """Los antivirus de los buzones abren los enlaces: si el GET verificara, el filtro
    gastaria el enlace antes que la persona."""
    _alta(_anonimo())
    token = _token(buzon[0], "verificar")
    c = _anonimo()
    c.get(f"/verificar/{token}")
    assert get_usuario_por_email("ana@ejemplo.com")["email_verificado_en"] is None
    r = c.post(f"/verificar/{token}", follow_redirects=False)
    assert r.headers["location"] == "/config/activo"
    assert get_usuario_por_email("ana@ejemplo.com")["email_verificado_en"] is not None


def test_el_enlace_de_verificacion_sirve_una_sola_vez(buzon):
    _alta(_anonimo())
    token = _token(buzon[0], "verificar")
    _anonimo().post(f"/verificar/{token}")
    r = _anonimo().post(f"/verificar/{token}")
    assert r.status_code == 400 and "venció o ya se usó" in r.text


def test_sin_verificar_no_se_entra_al_panel(buzon):
    _alta(_anonimo())
    c = _anonimo()
    c.post("/entrar", data={"email": "ana@ejemplo.com", "password": "clave-muy-segura"})
    assert c.get("/", follow_redirects=False).headers["location"] == "/verificar-aviso"


def test_reenviar_invalida_el_enlace_anterior(buzon):
    _alta(_anonimo())
    viejo = _token(buzon[0], "verificar")
    c = _anonimo()
    c.post("/entrar", data={"email": "ana@ejemplo.com", "password": "clave-muy-segura"})
    c.post("/verificar-aviso/reenviar")
    assert len(buzon) == 2
    assert _anonimo().post(f"/verificar/{viejo}").status_code == 400


# --- acceso ---


def test_correo_inexistente_y_clave_errada_dan_el_mismo_mensaje(buzon):
    nuevo_cliente()
    c = _anonimo()
    inexistente = c.post("/entrar", data={"email": "nadie@ejemplo.com", "password": "lo-que-sea-largo"})
    errada = c.post("/entrar", data={"email": "prueba@ejemplo.com", "password": "clave-equivocada"})
    assert inexistente.status_code == errada.status_code == 400
    assert "Correo o contraseña incorrectos" in inexistente.text
    assert "Correo o contraseña incorrectos" in errada.text


def test_cinco_fallos_bloquean_la_cuenta_un_rato(buzon):
    nuevo_cliente()
    c = _anonimo()
    for _ in range(5):
        c.post("/entrar", data={"email": "prueba@ejemplo.com", "password": "clave-equivocada"})
    # Ni siquiera la clave correcta entra mientras dura el bloqueo.
    r = c.post("/entrar", data={"email": "prueba@ejemplo.com", "password": PASSWORD_PRUEBA})
    assert r.status_code == 400 and "Demasiados intentos" in r.text


def test_salir_cierra_la_sesion(buzon):
    c = nuevo_cliente()
    assert c.get("/", follow_redirects=False).status_code == 200
    c.post("/salir")
    assert c.get("/", follow_redirects=False).headers["location"] == "/entrar"


# --- CSRF ---


def test_post_sin_token_csrf_se_rechaza(buzon):
    c = nuevo_cliente()
    r = c.post("/config/activo", data={"nombre": "X", "csrf_token": "falso"})
    assert r.status_code == 403


def test_post_desde_otro_sitio_se_rechaza(buzon):
    c = nuevo_cliente()
    r = c.post("/salir", headers={"Origin": "https://sitio-malicioso.com"})
    assert r.status_code == 403
    assert c.get("/", follow_redirects=False).status_code == 200  # la sesión sigue viva


# --- recuperacion ---


def test_recuperar_responde_igual_exista_o_no_la_cuenta(buzon):
    nuevo_cliente()
    existe = _anonimo().post("/recuperar", data={"email": "prueba@ejemplo.com"})
    no_existe = _anonimo().post("/recuperar", data={"email": "nadie@ejemplo.com"})
    assert existe.text.count("te enviamos un enlace") == no_existe.text.count("te enviamos un enlace") == 1
    assert len(buzon) == 1


def test_recuperar_cambia_la_clave_y_cierra_las_otras_sesiones(buzon):
    vieja = nuevo_cliente()
    _anonimo().post("/recuperar", data={"email": "prueba@ejemplo.com"})
    token = _token(buzon[0], "recuperar")
    nueva = _anonimo()
    r = nueva.post(f"/recuperar/{token}", data={"password": "clave-nueva-larga", "confirmacion": "clave-nueva-larga"},
                   follow_redirects=False)
    assert r.headers["location"].startswith("/cuenta")
    assert vieja.get("/", follow_redirects=False).headers["location"] == "/entrar"
    assert nueva.get("/", follow_redirects=False).status_code == 200


def test_un_error_de_tipeo_no_quema_el_enlace_de_recuperacion(buzon):
    nuevo_cliente()
    _anonimo().post("/recuperar", data={"email": "prueba@ejemplo.com"})
    token = _token(buzon[0], "recuperar")
    c = _anonimo()
    c.post(f"/recuperar/{token}", data={"password": "clave-nueva-larga", "confirmacion": "no-coincide-xx"})
    r = c.post(f"/recuperar/{token}", data={"password": "clave-nueva-larga", "confirmacion": "clave-nueva-larga"},
               follow_redirects=False)
    assert r.status_code == 303


# --- perfil ---


def test_cambiar_la_clave_cierra_las_demas_sesiones_pero_no_la_propia(buzon):
    otra = nuevo_cliente()
    propia = nuevo_cliente()
    propia.post("/cuenta/password", data={"actual": PASSWORD_PRUEBA, "password": "clave-nueva-larga",
                "confirmacion": "clave-nueva-larga"})
    assert propia.get("/", follow_redirects=False).status_code == 200
    assert otra.get("/", follow_redirects=False).headers["location"] == "/entrar"


def test_cambiar_la_clave_exige_la_actual(buzon):
    c = nuevo_cliente()
    r = c.post("/cuenta/password", data={"actual": "no-es-la-actual", "password": "clave-nueva-larga",
               "confirmacion": "clave-nueva-larga"})
    assert r.status_code == 400 and "actual no es correcta" in r.text


def test_eliminar_la_cuenta_borra_todo(buzon):
    c = nuevo_cliente()
    c.post("/config/activo", data={"nombre": "Para borrar", "tipo": "coliving", "unidades_totales": "2",
           "comision_administrador_pct": "10", "moneda": "COP"})
    r = c.post("/cuenta/eliminar", data={"password": PASSWORD_PRUEBA})
    assert "Cuenta eliminada" in r.text
    assert get_usuario_por_email("prueba@ejemplo.com") is None
    assert c.get("/", follow_redirects=False).headers["location"] == "/entrar"


def test_eliminar_la_cuenta_exige_la_contrasena(buzon):
    c = nuevo_cliente()
    r = c.post("/cuenta/eliminar", data={"password": "equivocada-xx"})
    assert r.status_code == 400 and "No se borró nada" in r.text
    assert get_usuario_por_email("prueba@ejemplo.com") is not None


# --- asesoria por invitacion y administracion ---


def test_sin_permiso_la_asesoria_no_llama_al_modelo(buzon, monkeypatch):
    llamadas = []
    monkeypatch.setattr("web.routes.generar_y_guardar", lambda *a, **k: llamadas.append(1))
    c = nuevo_cliente(asesoria=False)
    c.post("/config/activo", data={"nombre": "X", "tipo": "coliving", "unidades_totales": "2",
           "comision_administrador_pct": "10", "moneda": "COP"})
    r = c.post("/asesoria/2026/7", data={"origen": "historico"}, follow_redirects=False)
    assert "no%20est%C3%A1%20habilitada" in r.headers["location"]
    assert llamadas == []


def test_quien_no_es_admin_no_entra_a_admin(buzon):
    c = nuevo_cliente()
    assert c.get("/admin", follow_redirects=False).headers["location"] == "/"


def test_el_admin_habilita_la_asesoria_de_otra_cuenta(buzon):
    nuevo_cliente("beto@ejemplo.com")
    admin = nuevo_cliente("admin@ejemplo.com")
    from db.connection import db_cursor
    with db_cursor(privilegiado=True) as cur:
        cur.execute("UPDATE usuario SET es_admin = true WHERE email = 'admin@ejemplo.com'")
    beto_id = get_usuario_por_email("beto@ejemplo.com")["id"]
    assert "beto@ejemplo.com" in admin.get("/admin").text
    admin.post(f"/admin/cuentas/{beto_id}/asesoria", data={"habilitar": "1"})
    assert get_usuario_por_email("beto@ejemplo.com")["asesoria_habilitada"] is True
    set_asesoria_habilitada(beto_id, False)


def test_quien_no_es_admin_no_puede_habilitarse_la_asesoria(buzon):
    c = nuevo_cliente()
    propio = get_usuario_por_email("prueba@ejemplo.com")["id"]
    c.post(f"/admin/cuentas/{propio}/asesoria", data={"habilitar": "1"})
    assert get_usuario_por_email("prueba@ejemplo.com")["asesoria_habilitada"] is False
