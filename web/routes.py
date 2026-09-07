"""Rutas de la aplicación.

Implementadas: panel (estado sin activo), configuración del activo y de los umbrales.
Todavía como marcadores: el registro mensual y la vista del mes.
"""
from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db.repositorio import (
    agregar_capex,
    agregar_recordatorio,
    crear_o_actualizar_activo,
    eliminar_capex,
    eliminar_recordatorio,
    get_activo,
    get_capex,
    get_configuracion,
    get_contrato_maestro,
    get_asesoria,
    get_politica,
    get_recordatorios,
    get_reporte,
    get_reportes,
    get_reserva_movimientos,
    guardar_contrato_maestro,
    guardar_politica,
    guardar_reporte,
    set_configuracion,
)
from dominio.asesoria import generar_y_guardar
from dominio.capex import resumen_capex
from dominio.panel import meses_registrados, panel_mes
from dominio.configuracion import (
    CLAVES_CONFIGURACION,
    categorias_recordatorio,
    horizonte_destino,
)
from dominio.configuracion import horizonte_meses as horizonte_meses_config
from dominio.consolidado import consolidar_historico
from dominio.diagnostico import diagnostico_mes
from dominio.recordatorios import calcular_proxima_fecha, clasificar_recordatorios
from dominio.reserva import recalcular_reserva
from motor.politica import calcular_brecha
from motor.recordatorios import PROXIMO, VENCIDO
from motor.reserva import meses_restantes, reserva_agotada
from web.templates_env import templates

router = APIRouter()

MONEDAS = ("COP", "USD")
TIPOS_ACTIVO = ("coliving", "local comercial", "bodega", "otro")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _hoy() -> str:
    return date.today().isoformat()


def _num(crudo: str, etiqueta: str, errores: list, *, entero=False, minimo=None, maximo=None):
    try:
        valor = int(crudo) if entero else float(crudo)
    except (TypeError, ValueError):
        errores.append(f"{etiqueta}: debe ser un número.")
        return None
    if minimo is not None and valor < minimo:
        errores.append(f"{etiqueta}: no puede ser menor que {minimo}.")
        return None
    if maximo is not None and valor > maximo:
        errores.append(f"{etiqueta}: no puede ser mayor que {maximo}.")
        return None
    return valor


def _fmt_num(valor) -> str:
    """Guarda el entero sin la coma decimal sobrante cuando el flotante es entero."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


@router.get("/", response_class=HTMLResponse)
def panel(request: Request) -> HTMLResponse:
    activo = get_activo()
    if not activo:
        return templates.TemplateResponse(
            request, "panel.html", {"active": "panel", "activo": None}
        )
    meses = meses_registrados(activo["id"])
    if not meses:
        return templates.TemplateResponse(
            request, "panel.html", {"active": "panel", "activo": activo, "sin_historico": True}
        )
    try:
        anio = int(request.query_params.get("anio") or meses[0][0])
        mes = int(request.query_params.get("mes") or meses[0][1])
    except ValueError:
        anio, mes = meses[0]
    datos = panel_mes(activo["id"], anio, mes) or panel_mes(activo["id"], *meses[0])
    return templates.TemplateResponse(
        request,
        "panel.html",
        {
            "active": "panel",
            "activo": activo,
            "meses": meses,
            "nombres_mes": MESES,
            **datos,
        },
    )


@router.get("/config", response_class=HTMLResponse)
def config(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    conf = get_configuracion(activo["id"])
    clasificados = clasificar_recordatorios(get_recordatorios(activo["id"]), conf)
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "active": "config",
            "activo": activo,
            "conf": conf,
            "claves": CLAVES_CONFIGURACION,
            "contrato": get_contrato_maestro(activo["id"]),
            "politica": get_politica(activo["id"]),
            "capex": get_capex(activo["id"]),
            "recordatorios_total": len(clasificados),
            "recordatorios_vencidos": sum(1 for _, e in clasificados if e.estado == VENCIDO),
            "recordatorios_proximos": sum(1 for _, e in clasificados if e.estado == PROXIMO),
        },
    )


@router.get("/config/activo", response_class=HTMLResponse)
def config_activo_form(request: Request) -> HTMLResponse:
    activo = get_activo()
    return templates.TemplateResponse(
        request,
        "config_activo.html",
        {
            "active": "config",
            "activo": activo,
            "modo": "editar" if activo else "crear",
            "monedas": MONEDAS,
            "tipos": TIPOS_ACTIVO,
            "errores": [],
        },
    )


@router.post("/config/activo", response_class=HTMLResponse)
def config_activo_guardar(
    request: Request,
    nombre: str = Form(""),
    tipo: str = Form(""),
    unidades_totales: str = Form(""),
    comision_administrador_pct: str = Form(""),
    moneda: str = Form("COP"),
    ubicacion: str = Form(""),
    notas: str = Form(""),
):
    errores: list[str] = []
    if not nombre.strip():
        errores.append("El nombre es obligatorio.")
    try:
        unidades = int(unidades_totales)
        if unidades <= 0:
            errores.append("Las unidades deben ser un número mayor que cero.")
    except ValueError:
        unidades = None
        errores.append("Las unidades deben ser un número entero.")
    try:
        comision = float(comision_administrador_pct)
        if not 0 <= comision <= 100:
            errores.append("La comisión debe estar entre 0 y 100.")
    except ValueError:
        comision = None
        errores.append("La comisión debe ser un número.")
    if moneda not in MONEDAS:
        errores.append("Moneda no válida.")

    if errores:
        crudo = {
            "nombre": nombre,
            "tipo": tipo,
            "unidades_totales": unidades_totales,
            "comision_administrador_pct": comision_administrador_pct,
            "moneda": moneda,
            "ubicacion": ubicacion,
            "notas": notas,
        }
        return templates.TemplateResponse(
            request,
            "config_activo.html",
            {
                "active": "config",
                "activo": crudo,
                "modo": "editar" if get_activo() else "crear",
                "monedas": MONEDAS,
                "tipos": TIPOS_ACTIVO,
                "errores": errores,
            },
            status_code=400,
        )

    crear_o_actualizar_activo(
        {
            "nombre": nombre.strip(),
            "tipo": tipo.strip() or "otro",
            "unidades_totales": unidades,
            "comision_administrador_pct": comision,
            "moneda": moneda,
            "ubicacion": ubicacion.strip(),
            "notas": notas.strip(),
        }
    )
    return RedirectResponse("/config", status_code=303)


@router.get("/config/umbrales", response_class=HTMLResponse)
def config_umbrales_form(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    return templates.TemplateResponse(
        request,
        "config_umbrales.html",
        {
            "active": "config",
            "activo": activo,
            "claves": CLAVES_CONFIGURACION,
            "conf": get_configuracion(activo["id"]),
            "errores": [],
        },
    )


@router.post("/config/umbrales", response_class=HTMLResponse)
async def config_umbrales_guardar(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    form = await request.form()
    errores: list[str] = []
    limpios: dict[str, object] = {}
    for clave in CLAVES_CONFIGURACION:
        crudo = (form.get(clave.clave) or "").strip()
        if crudo == "":
            continue
        if clave.tipo == "texto":
            limpios[clave.clave] = crudo
            continue
        try:
            valor = int(crudo) if clave.tipo == "int" else float(crudo)
        except ValueError:
            errores.append(f"{clave.etiqueta}: debe ser un número.")
            continue
        if valor < 0:
            errores.append(f"{clave.etiqueta}: no puede ser negativo.")
            continue
        limpios[clave.clave] = valor

    if errores:
        conf = {**get_configuracion(activo["id"])}
        conf.update({k: form.get(k) for k in form})
        return templates.TemplateResponse(
            request,
            "config_umbrales.html",
            {
                "active": "config",
                "activo": activo,
                "claves": CLAVES_CONFIGURACION,
                "conf": conf,
                "errores": errores,
            },
            status_code=400,
        )

    for clave, valor in limpios.items():
        set_configuracion(activo["id"], clave, _fmt_num(valor))
    return RedirectResponse("/config", status_code=303)


@router.get("/config/contrato", response_class=HTMLResponse)
def config_contrato_form(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    return templates.TemplateResponse(
        request,
        "config_contrato.html",
        {"active": "config", "contrato": get_contrato_maestro(activo["id"]), "errores": []},
    )


@router.post("/config/contrato", response_class=HTMLResponse)
def config_contrato_guardar(
    request: Request,
    canon_mensual: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_vencimiento: str = Form(""),
    vigencia_meses: str = Form(""),
    regla_reajuste: str = Form(""),
    ventana_preaviso_dias: str = Form("0"),
):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    errores: list[str] = []
    canon = _num(canon_mensual, "Canon mensual", errores, minimo=0)
    vigencia = _num(vigencia_meses, "Vigencia (meses)", errores, entero=True, minimo=1)
    preaviso = _num(ventana_preaviso_dias or "0", "Ventana de preaviso", errores, entero=True, minimo=0)
    if not fecha_inicio:
        errores.append("La fecha de inicio es obligatoria.")
    if not fecha_vencimiento:
        errores.append("La fecha de vencimiento es obligatoria.")

    if errores:
        crudo = {
            "canon_mensual": canon_mensual,
            "fecha_inicio": fecha_inicio,
            "fecha_vencimiento": fecha_vencimiento,
            "vigencia_meses": vigencia_meses,
            "regla_reajuste": regla_reajuste,
            "ventana_preaviso_dias": ventana_preaviso_dias,
        }
        return templates.TemplateResponse(
            request,
            "config_contrato.html",
            {"active": "config", "contrato": crudo, "errores": errores},
            status_code=400,
        )

    guardar_contrato_maestro(
        activo["id"],
        {
            "canon_mensual": canon,
            "fecha_inicio": fecha_inicio,
            "fecha_vencimiento": fecha_vencimiento,
            "vigencia_meses": vigencia,
            "regla_reajuste": regla_reajuste.strip(),
            "ventana_preaviso_dias": preaviso,
            "fecha_definicion": _hoy(),
        },
    )
    recalcular_reserva(activo["id"])  # el canon cambia el resultado de todos los periodos
    return RedirectResponse("/config", status_code=303)


@router.get("/config/politica", response_class=HTMLResponse)
def config_politica_form(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    return templates.TemplateResponse(
        request,
        "config_politica.html",
        {"active": "config", "politica": get_politica(activo["id"]), "errores": []},
    )


@router.post("/config/politica", response_class=HTMLResponse)
def config_politica_guardar(
    request: Request,
    porcentaje_libre: str = Form(""),
    porcentaje_reinversion: str = Form(""),
    porcentaje_reserva: str = Form(""),
    tarifa_marginal_actual: str = Form("0"),
    calcular_impuesto: str = Form(""),
):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    errores: list[str] = []
    libre = _num(porcentaje_libre, "Libre disposición", errores, minimo=0, maximo=100)
    reinv = _num(porcentaje_reinversion, "Reinversión", errores, minimo=0, maximo=100)
    reserva = _num(porcentaje_reserva, "Reserva de contingencia", errores, minimo=0, maximo=100)
    calcula = calcular_impuesto == "1"
    tarifa = 0.0
    if calcula:
        tarifa = _num(tarifa_marginal_actual or "0", "Tarifa marginal", errores, minimo=0, maximo=39) or 0.0

    if not errores and abs(libre + reinv + reserva - 100) >= 0.01:
        errores.append(
            f"Los tres porcentajes deben sumar exactamente 100. Ahora suman "
            f"{libre + reinv + reserva:g}."
        )

    if errores:
        crudo = {
            "porcentaje_libre": porcentaje_libre,
            "porcentaje_reinversion": porcentaje_reinversion,
            "porcentaje_reserva": porcentaje_reserva,
            "tarifa_marginal_actual": tarifa_marginal_actual,
            "calcular_impuesto": 1 if calcula else 0,
        }
        return templates.TemplateResponse(
            request,
            "config_politica.html",
            {"active": "config", "politica": crudo, "errores": errores},
            status_code=400,
        )

    guardar_politica(
        activo["id"],
        {
            "porcentaje_libre": libre,
            "porcentaje_reinversion": reinv,
            "porcentaje_reserva": reserva,
            "tarifa_marginal_actual": tarifa,
            "calcular_impuesto": 1 if calcula else 0,
            "fecha_definicion": _hoy(),
        },
    )
    recalcular_reserva(activo["id"])  # el % de reserva cambia la trayectoria del fondo
    return RedirectResponse("/config", status_code=303)


@router.get("/config/capex", response_class=HTMLResponse)
def config_capex_vista(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    contrato = get_contrato_maestro(activo["id"])
    conf = get_configuracion(activo["id"])
    horizonte_sugerido = contrato["vigencia_meses"] if contrato else horizonte_meses_config(conf)
    partidas = get_capex(activo["id"])
    return templates.TemplateResponse(
        request,
        "config_capex.html",
        {
            "active": "config",
            "capex": partidas,
            "resumen": resumen_capex(partidas) if partidas else None,
            "horizonte_sugerido": horizonte_sugerido,
            "moneda": activo["moneda"],
            "errores": [],
        },
    )


@router.post("/config/capex", response_class=HTMLResponse)
def config_capex_agregar(
    request: Request,
    concepto: str = Form(""),
    monto: str = Form(""),
    fecha: str = Form(""),
    horizonte_meses: str = Form(""),
):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    errores: list[str] = []
    if not concepto.strip():
        errores.append("El concepto es obligatorio.")
    monto_val = _num(monto, "Monto", errores, minimo=0)
    horizonte_val = _num(horizonte_meses, "Horizonte (meses)", errores, entero=True, minimo=1)
    if not fecha:
        errores.append("La fecha es obligatoria.")

    if errores:
        contrato = get_contrato_maestro(activo["id"])
        conf = get_configuracion(activo["id"])
        partidas = get_capex(activo["id"])
        return templates.TemplateResponse(
            request,
            "config_capex.html",
            {
                "active": "config",
                "capex": partidas,
                "resumen": resumen_capex(partidas) if partidas else None,
                "horizonte_sugerido": contrato["vigencia_meses"] if contrato else horizonte_meses_config(conf),
                "moneda": activo["moneda"],
                "errores": errores,
            },
            status_code=400,
        )

    agregar_capex(
        activo["id"],
        {
            "concepto": concepto.strip(),
            "monto": monto_val,
            "fecha": fecha,
            "horizonte_meses": horizonte_val,
        },
    )
    return RedirectResponse("/config/capex", status_code=303)


@router.post("/config/capex/{capex_id}/eliminar", response_class=HTMLResponse)
def config_capex_eliminar(request: Request, capex_id: int):
    activo = get_activo()
    if activo:
        eliminar_capex(activo["id"], capex_id)
    return RedirectResponse("/config/capex", status_code=303)


@router.get("/config/recordatorios", response_class=HTMLResponse)
def config_recordatorios_vista(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    conf = get_configuracion(activo["id"])
    return templates.TemplateResponse(
        request,
        "config_recordatorios.html",
        {
            "active": "config",
            "clasificados": clasificar_recordatorios(get_recordatorios(activo["id"]), conf),
            "categorias": categorias_recordatorio(conf),
            "errores": [],
        },
    )


@router.post("/config/recordatorios", response_class=HTMLResponse)
def config_recordatorios_agregar(
    request: Request,
    categoria: str = Form(""),
    descripcion: str = Form(""),
    ultima_fecha: str = Form(""),
    frecuencia_meses: str = Form(""),
    fecha_vencimiento_fija: str = Form(""),
):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    errores: list[str] = []
    if not categoria.strip():
        errores.append("La categoría es obligatoria.")
    if not descripcion.strip():
        errores.append("La descripción es obligatoria.")

    frecuencia = None
    if frecuencia_meses.strip():
        frecuencia = _num(frecuencia_meses, "Frecuencia (meses)", errores, entero=True, minimo=1)
        if frecuencia is not None and not ultima_fecha:
            errores.append("Con frecuencia hay que dar también la última fecha.")
    elif not fecha_vencimiento_fija:
        errores.append("El recordatorio necesita una frecuencia con última fecha, o una fecha de vencimiento fija.")

    if not errores:
        datos = {
            "categoria": categoria.strip(),
            "descripcion": descripcion.strip(),
            "ultima_fecha": ultima_fecha or None,
            "frecuencia_meses": frecuencia,
            "fecha_vencimiento_fija": fecha_vencimiento_fija or None,
            "proxima_fecha": None,
        }
        try:
            datos["proxima_fecha"] = calcular_proxima_fecha(datos).isoformat()
        except ValueError as exc:
            errores.append(str(exc))

    if errores:
        conf = get_configuracion(activo["id"])
        return templates.TemplateResponse(
            request,
            "config_recordatorios.html",
            {
                "active": "config",
                "clasificados": clasificar_recordatorios(get_recordatorios(activo["id"]), conf),
                "categorias": categorias_recordatorio(conf),
                "errores": errores,
            },
            status_code=400,
        )

    agregar_recordatorio(activo["id"], datos)
    return RedirectResponse("/config/recordatorios", status_code=303)


@router.post("/config/recordatorios/{recordatorio_id}/eliminar", response_class=HTMLResponse)
def config_recordatorios_eliminar(request: Request, recordatorio_id: int):
    activo = get_activo()
    if activo:
        eliminar_recordatorio(activo["id"], recordatorio_id)
    return RedirectResponse("/config/recordatorios", status_code=303)


def _filas_unidades(activo, previas: dict) -> list[dict]:
    """previas: {unidad_label: {arrendada, ingreso}}"""
    filas = []
    for i in range(1, activo["unidades_totales"] + 1):
        label = f"Unidad {i}"
        p = previas.get(label, {})
        filas.append(
            {
                "i": i,
                "label": label,
                "arrendada": bool(p.get("arrendada")),
                "ingreso": p.get("ingreso", ""),
            }
        )
    return filas


@router.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request, anio: int | None = None, mes: int | None = None):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    hoy = date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    reporte, unidades_prev = get_reporte(activo["id"], anio, mes)
    previas = {
        u["unidad_label"]: {"arrendada": u["arrendada"], "ingreso": u["ingreso_inquilino"]}
        for u in unidades_prev
    }
    datos = {
        "gastos_fijos": reporte["gastos_fijos"] if reporte else "",
        "gastos_variables": reporte["gastos_variables"] if reporte else "",
        "comision_admin": reporte["comision_admin"] if reporte else "",
        "novedades": reporte["novedades"] if reporte else "",
    }
    return templates.TemplateResponse(
        request,
        "registro.html",
        {
            "active": "registro",
            "activo": activo,
            "anio": anio,
            "mes": mes,
            "meses": MESES,
            "filas": _filas_unidades(activo, previas),
            "datos": datos,
            "editando": reporte is not None,
            "errores": [],
        },
    )


@router.post("/registro", response_class=HTMLResponse)
async def registro_guardar(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)

    form = await request.form()
    errores: list[str] = []
    mes = _num(form.get("mes"), "Mes", errores, entero=True, minimo=1, maximo=12)
    anio = _num(form.get("anio"), "Año", errores, entero=True, minimo=2000)
    gastos_fijos = _num(form.get("gastos_fijos"), "Gastos fijos", errores, minimo=0)
    gastos_variables = _num(form.get("gastos_variables"), "Gastos variables", errores, minimo=0)
    comision = _num(form.get("comision_admin"), "Comisión del administrador", errores, minimo=0)

    unidades: list[dict] = []
    previas: dict = {}
    arrendadas = 0
    for i in range(1, activo["unidades_totales"] + 1):
        label = f"Unidad {i}"
        marcada = form.get(f"unidad_{i}_arrendada") == "1"
        ingreso_raw = (form.get(f"unidad_{i}_ingreso") or "").strip()
        ingreso = 0.0
        if marcada:
            arrendadas += 1
            valor = _num(ingreso_raw, f"Ingreso de la unidad {i}", errores, minimo=0) if ingreso_raw else None
            if valor is None:
                errores.append(f"La unidad {i} está marcada como arrendada pero sin ingreso.")
            elif valor <= 0:
                errores.append(f"El ingreso de la unidad {i} debe ser mayor que cero.")
            else:
                ingreso = valor
        elif ingreso_raw:
            valor = _num(ingreso_raw, f"Ingreso de la unidad {i}", errores, minimo=0)
            ingreso = valor or 0.0
        unidades.append(
            {"unidad_label": label, "arrendada": 1 if marcada else 0, "ingreso_inquilino": ingreso}
        )
        previas[label] = {"arrendada": marcada, "ingreso": ingreso_raw}

    if arrendadas > activo["unidades_totales"]:
        errores.append("La ocupación no puede superar las unidades del activo.")

    if errores:
        return templates.TemplateResponse(
            request,
            "registro.html",
            {
                "active": "registro",
                "activo": activo,
                "anio": form.get("anio") or date.today().year,
                "mes": int(form.get("mes")) if (form.get("mes") or "").isdigit() else date.today().month,
                "meses": MESES,
                "filas": _filas_unidades(activo, previas),
                "datos": {
                    "gastos_fijos": form.get("gastos_fijos") or "",
                    "gastos_variables": form.get("gastos_variables") or "",
                    "comision_admin": form.get("comision_admin") or "",
                    "novedades": form.get("novedades") or "",
                },
                "editando": False,
                "errores": errores,
            },
            status_code=400,
        )

    guardar_reporte(
        activo["id"],
        {
            "mes": mes,
            "anio": anio,
            "gastos_fijos": gastos_fijos,
            "gastos_variables": gastos_variables,
            "comision_admin": comision,
            "novedades": (form.get("novedades") or "").strip(),
            "fecha_registro": _hoy(),
        },
        unidades,
    )
    recalcular_reserva(activo["id"])
    return RedirectResponse("/historico", status_code=303)


@router.get("/historico", response_class=HTMLResponse)
def historico(request: Request):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    reportes = get_reportes(activo["id"])
    contrato = get_contrato_maestro(activo["id"])
    politica = get_politica(activo["id"])
    consolidado = consolidar_historico(reportes, contrato)
    movimientos = {
        (m["anio"], m["mes"]): m for m in get_reserva_movimientos(activo["id"])
    }

    filas = []
    for r, c in zip(reportes, consolidado):
        mov = movimientos.get((r["anio"], r["mes"]))
        brecha = (
            calcular_brecha(
                c.resultado,
                politica["porcentaje_libre"],
                politica["porcentaje_reinversion"],
                politica["porcentaje_reserva"],
            )
            if politica
            else None
        )
        filas.append(
            {
                "anio": r["anio"],
                "mes": r["mes"],
                "ocupacion": r["ocupacion"],
                "ingreso": c.ingreso,
                "costos_variables": c.costos_variables,
                "obligacion_fija": c.obligacion_fija,
                "resultado": c.resultado,
                "brecha": brecha,
                "reserva_monto": mov["monto"] if mov else None,
                "reserva_saldo": mov["saldo_resultante"] if mov else None,
                "diagnostico": diagnostico_mes(activo["id"], r["anio"], r["mes"]),
                "tiene_asesoria": get_asesoria(activo["id"], r["anio"], r["mes"]) is not None,
            }
        )

    # Estado del fondo: filas[0] es el mes más reciente (orden descendente).
    reserva_saldo = filas[0]["reserva_saldo"] if filas else None
    ultimo_resultado = filas[0]["resultado"] if filas else 0.0
    meses_rest = (
        meses_restantes(reserva_saldo, -ultimo_resultado)
        if reserva_saldo is not None and ultimo_resultado < 0
        else None
    )
    return templates.TemplateResponse(
        request,
        "historico.html",
        {
            "active": "historico",
            "activo": activo,
            "filas": filas,
            "meses": MESES,
            "sin_contrato": contrato is None,
            "sin_politica": politica is None,
            "reserva_saldo": reserva_saldo,
            "meses_restantes": meses_rest,
            "reserva_agotada": reserva_saldo is not None and reserva_agotada(reserva_saldo),
            "error_asesoria": request.query_params.get("error_asesoria"),
        },
    )


@router.get("/asesoria/{anio}/{mes}", response_class=HTMLResponse)
def asesoria_vista(request: Request, anio: int, mes: int):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    asesoria = get_asesoria(activo["id"], anio, mes)
    if not asesoria:
        return RedirectResponse("/historico", status_code=303)
    return templates.TemplateResponse(
        request,
        "asesoria.html",
        {"active": "historico", "activo": activo, "asesoria": asesoria,
         "mes_label": f"{MESES[mes - 1].capitalize()} {anio}"},
    )


@router.post("/asesoria/{anio}/{mes}", response_class=HTMLResponse)
def asesoria_generar(request: Request, anio: int, mes: int):
    activo = get_activo()
    if not activo:
        return RedirectResponse("/config/activo", status_code=303)
    resultado = generar_y_guardar(activo["id"], anio, mes)
    if not resultado.ok:
        from urllib.parse import quote

        return RedirectResponse(
            f"/historico?error_asesoria={quote(resultado.error)}", status_code=303
        )
    return RedirectResponse(f"/asesoria/{anio}/{mes}", status_code=303)
