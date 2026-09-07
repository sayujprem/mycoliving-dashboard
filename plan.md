# Plan de implementación — MyColiving Dashboard

## Estado de avance (2026-08-31)

- **Tarea 1 — hecha y verificada.** Esqueleto FastAPI, carpetas `motor/` `dominio/` `db/`
  `web/`, `config.py`, `requirements.txt`, `.venv/`, `README.md`. `uvicorn main:app`
  responde 200; `tests/test_smoke.py` pasa.
- **Tarea 2 — hecha y verificada.** `db/schema.sql` (10 tablas + triggers de ocupación),
  `db/init_db.py`, `tests/conftest.py`, `tests/test_modelo_datos.py`. Suite: 9 tests pasan.
- **Tarea 2b — hecha y verificada.** `web/static/app.css` (tokens v2), `base.html` (shell:
  brand + nav), `web/templates/_macros.html` (chip, semaforo, stat, alert, recordatorio_row,
  brecha_row), `index.html` reescrito, rutas stub `/config` `/registro` `/historico`,
  `/static` montado. 11 tests pasan.
- **Tarea 3 — hecha y verificada.** `dominio/configuracion.py`, `db/repositorio.py`,
  rutas y plantillas de `/config`, `/config/activo`, `/config/umbrales`. 18 tests pasan;
  sin cifras de negocio en archivos de lógica.
- **Tarea 4 — hecha y verificada.** Formularios y rutas de contrato maestro, política de
  distribución (rechaza suma ≠ 100 y tarifa fuera de 0–39) y capex. 27 tests pasan.
- **Tarea 5 — hecha y verificada.** Registro mensual (`/registro`, una fila por unidad,
  deriva ocupación e ingreso de subarriendo) e histórico (`/historico`). Valida ocupación
  ≤ unidades y campos vacíos. 34 tests pasan; recorrido end-to-end en vivo OK.
- **Tarea 6 — hecha y verificada.** `motor/resultado.py` (genérico, sin dominio),
  `dominio/consolidado.py` (adaptador), `/historico` con `resultado_mes = ingreso −
  comisión − gastos − canon_maestro`. 39 tests pasan.
- **Tarea 7 — hecha y verificada.** Brecha automática por la política; `motor/politica.py`,
  `motor/reserva.py`, `dominio/reserva.py`. `/historico` muestra el fondo de reserva y su
  movimiento por mes. 47 tests pasan.
- **Tarea 8 — hecha y verificada.** `motor/capex.py`, `dominio/capex.py`; `/config/capex`
  muestra recuperación total y por partida. 54 tests.
- **Tarea 9 — hecha y verificada.** `motor/recordatorios.py`, `dominio/recordatorios.py`,
  CRUD `/config/recordatorios`; categorías y ventana desde `configuracion_dominio`.
- **Tarea 10 — hecha.** `dominio/semaforo.py` + `dominio/diagnostico.py` (semáforo de
  resultado y de ocupación con regla de vacancia; explicaciones con plantillas).
- **Tarea 11 — hecha.** `dominio/fiscal.py`, único archivo con conocimiento fiscal.
- **Tarea 12 — hecha.** `motor/asesor_ia.py`, cliente de Anthropic con `tool_choice`
  forzado, esquema validado y errores que no tumban la app.
- **Tarea 13 — hecha (salvo corrida real).** `dominio/asesoria.py`, rutas
  `/asesoria/{anio}/{mes}`, `asesoria.html`. La llamada real la verifica Nelson con su key.
- **Tarea 14 — hecha.** `dominio/panel.py` + `panel.html` (layout v2, tres columnas, la
  sustancia de spec.md). Navegación mes anterior/siguiente.
- **Tarea 15 — hecha.** `Diagnostico.vacancia_en_espera`; el panel avisa mientras no haya
  suficientes meses y la regla de vacancia no se dispara con un solo mes.
- **Tarea 16 — hecha.** `scripts/seed_coliving.py` (idempotente) + README completo.
- **Tarea 17 — hecha.** README documenta el recordatorio mensual por calendario.
- **LAS 17 TAREAS ESTÁN HECHAS.** Recorrido end-to-end en servidor real siguiendo el README: OK.

## Ajuste de alcance — 2026-09-01

Nelson pidió la plataforma funcional **sin exigir el contrato maestro**: solo con el
registro mensual del informe y un **horizonte temporal ajustable**. Ver el detalle en
`ajustes-al-spec.md` § "Ajuste de alcance". Resumen: `contrato_maestro` es opcional en toda
la app (canon en 0 si no está, se asume incluido en `gastos_fijos`); nuevas claves de
configuración `horizonte_meses` y `horizonte_destino` reemplazan a la vigencia del contrato
como referencia por defecto para el capex y la asesoría; el panel muestra "Horizonte" en vez
de depender del contrato.

**109 tests pasan + 1 skipped (corrida real, opt-in con `MYCOLIVING_TEST_REAL_API=1`).**

## Asesoría real verificada — 2026-09-01

`ANTHROPIC_API_KEY` guardada en `.env` (gitignored, `chmod 600`, `python-dotenv` la carga).
La key es identity-linked: se agregó `ANTHROPIC_WORKSPACE_ID` (config → dominio → motor,
como header `anthropic-workspace-id`); el id del workspace (`wrkspc_...`) vive en `.env`.
`conftest.py` mantiene la suite sin gastar créditos salvo `MYCOLIVING_TEST_REAL_API=1`.
**Una generación real produjo asesoría concreta** (nombra la cifra, la causa, la reserva
agotada, el horizonte) con la advertencia de alcance en la nota fiscal. Tarea 13 cerrada.

**Plataforma entregada y funcional.** Falta solo que Nelson cargue sus datos reales y pase
`verify-after-changes` cuando quiera.

## Diseño v2 — resuelto

`My Coliving Dashboard v2.dc.html` (Claude Design) es una pieza de Claude Design que usa
React + `dc-runtime` (`support.js`), lo cual choca con la restricción "sin frameworks JS".
Se **porta a Jinja2 server-rendered**.

**Decisión: v2 es la piel, `spec.md` manda el fondo.**

Se toma de v2: tipografía (Manrope / Instrument Serif / JetBrains Mono), paleta (fondo
`#F4F4F4`, tinta `#0A0D03`, acento lima `#D0FD65`, panel oscuro `#0A0D03`/`#16190E`,
semáforo `#D0FD65` / `#FFD84D` / `#E5573F`), y el dashboard como una sola pantalla: panel
oscuro con tres columnas **Hacer** (recordatorios) · **Entender** (semáforo + panorama) ·
**Decidir** (brecha + asesoría), tarjetas blancas redondeadas, chips mono.

Se descarta de v2 (choca con decisiones cerradas): margen % como segundo semáforo (se
mantiene ocupación real vs. de equilibrio), `neto` sin restar canon maestro, tarjeta de
"horizonte patrimonial" (se reemplaza por "contrato maestro"), encuadre fiscal de
propietario (se mantiene subarriendo como renta no laboral con advertencia de alcance) y
las secciones de landing/marketing.

Piezas del plan que v2 no muestra y que se agregan al layout v2: recuperación de capex,
tracking de reserva en meses negativos, estado "primer mes sin histórico", advertencia
fiscal.

## Objetivo

Construir la v1 local del MyColiving Dashboard: una app web de un solo usuario que toma el
informe mensual de la inmobiliaria, produce un diagnóstico determinístico del mes (resultado
en pesos, ocupación real vs. de equilibrio, semáforos con explicación, brecha vs. la meta de
distribución, estado de la reserva, recuperación del capex), avisa de vencimientos, y genera
con IA un informe mensual de asesoría financiera y fiscal. El plan está cumplido cuando se
puede registrar un mes en menos de dos minutos y la vista del mes muestra las siete piezas
del diagnóstico más la asesoría.

## Contexto del problema

Nelson opera un coliving de 5 apartaestudios en modelo rent-to-rent: contrato maestro de
arriendo con la propietaria (con permiso de subarriendo) y contrato de administración con
una inmobiliaria que cobra 10% de lo recaudado. Cada mes llega un informe y hoy no hay
criterio sistemático para juzgarlo ni recordatorio de vencimientos ni asesoría fiscal sobre
ese ingreso. La restricción que manda el resultado es el canon fijo del contrato maestro
contra la ocupación variable, así que el sistema modela ese spread, no el inmueble.

## El spec de referencia

`MyColiving_dashboard/spec.md` (aprobado 2026-08-29). Fuente de verdad para cualquier duda
de alcance o comportamiento. Contexto de apoyo: `MyColiving_dashboard/evaluacion-negocio-producto.md`
y `MyColiving_dashboard/ajustes-al-spec.md`.

## Restricciones técnicas (del spec original, confirmadas)

- Python + FastAPI. SQLite. HTML renderizado en servidor con Jinja2, sin frameworks JS.
- IA solo para el informe de asesoría (Paso 5): API de Anthropic con `tools` e `input_schema`
  validado antes de enviar. El semáforo es determinístico, sin IA.
- Despliegue local, costo de infraestructura cero. Solo se paga el consumo del API.
- Estructura de carpetas con frontera visible `motor/` (independiente del tipo de activo y
  del país) y `dominio/` (subarriendo de inmuebles + Colombia). Todas las tablas de datos
  llevan `activo_id` aunque hoy solo exista un activo.

## Lista de tareas a implementar

### 1. Esqueleto del repositorio y app FastAPI
Crear la estructura con `motor/`, `dominio/`, `web/` (rutas + plantillas Jinja2 + layout
base), `db/` (conexión SQLite, script de init). Config por variables de entorno
(`ANTHROPIC_API_KEY`, ruta del `.db`).
**Hecho cuando:** `uvicorn` levanta en local y sirve una página base; las carpetas `motor/`
y `dominio/` existen con su README de una línea explicando la frontera.

### 2. Modelo de datos en SQLite
Tablas, todas con `activo_id`:
- `activo` (nombre, tipo, unidades_totales, comision_administrador_pct, moneda, ubicacion, notas)
- `contrato_maestro` (canon_mensual, fecha_inicio, fecha_vencimiento, vigencia_meses, regla_reajuste, ventana_preaviso_dias, fecha_definicion)
- `politica_distribucion` (porcentaje_libre, porcentaje_reinversion, porcentaje_reserva, tarifa_marginal_actual, calcular_impuesto bool, fecha_definicion)
- `configuracion_dominio` (clave, valor, descripcion) — umbrales editables
- `capex` (concepto, monto, fecha, horizonte_meses)
- `recordatorios` (categoria, descripcion, ultima_fecha, frecuencia_meses nullable, fecha_vencimiento_fija nullable, proxima_fecha calculada)
- `reporte_mensual` (mes, anio, gastos_fijos, gastos_variables, comision_admin, novedades, fecha_registro) + hija `reporte_unidad` (unidad_label, arrendada bool, ingreso_inquilino)
- `reserva_movimiento` (mes, anio, monto, saldo_resultante)
- `asesoria_generada` (mes, anio, semaforo_resultado, semaforo_ocupacion, resultado_mes, ocupacion_equilibrio, porcentaje_libre_real, brecha_frente_a_meta, capex_recuperado_pct, texto_asesoria, texto_fiscal, fecha_generacion)
**Hecho cuando:** el script de init crea el `.db`; un test verifica que cada tabla existe y
que insertar un `reporte_unidad` con más unidades arrendadas que `activo.unidades_totales`
falla la validación.

### 3. Alta y edición del `activo` y de `configuracion_dominio`
Formularios Jinja2. Claves de configuración con descripción en lenguaje simple:
`ocupacion_minima_verde`, `gasto_maximo_pct_verde`, `meses_consecutivos_baja_ocupacion_para_rojo`,
`arriendo_promedio_unidad`, `ventana_aviso_recordatorio_dias`. Ningún umbral ni el número de
unidades escrito en código.
**Hecho cuando:** se crea el activo y se edita cada umbral desde la interfaz y queda en la BD;
buscar en el repo el `5`, el `10%` y el rango de arriendo no los encuentra en archivos de lógica.

### 4. Formularios de `contrato_maestro`, `politica_distribucion` y `capex`
Validación: los tres porcentajes de la política suman exactamente 100, rechazo con mensaje si
no. `tarifa_marginal_actual` entre 0 y 39, o casilla "no calcular impuesto" que la desactiva.
`capex` con monto, fecha y `horizonte_meses` (valor por defecto = `contrato_maestro.vigencia_meses`,
tentativa de 60).
**Hecho cuando:** cada formulario guarda y valida; la política rechaza sumas distintas de 100.

### 5. Registro mensual del informe e histórico
Formulario: mes/año, una fila por unidad (arrendada sí/no, ingreso del inquilino), gastos
fijos, gastos variables, comisión 10%, novedades. El sistema deriva `ocupacion` (conteo de
arrendadas) e `ingreso_subarriendo` (suma de ingresos). Validaciones: ocupación ≤ unidades,
ingresos y gastos no vacíos. Vista de histórico en tabla.
**Hecho cuando:** en prueba manual se registra un mes completo en menos de dos minutos y
aparece en el histórico; los rechazos por ocupación y por campos vacíos funcionan.

### 6. (motor) Resultado del mes y vista consolidada
`resultado_mes = ingreso_subarriendo − comision_admin − (gastos_fijos + gastos_variables) − canon_maestro`.
Vista consolidada consultable cualquier día con el histórico de meses y sus semáforos. Este
módulo no menciona coliving, inmuebles ni Colombia.
**Hecho cuando:** un test con datos no inmobiliarios produce el `resultado_mes` correcto; la
vista consolidada carga con varios meses.

### 7. (motor) Brecha vs. política y tracking de reserva
`porcentaje_libre_real` del mes y brecha contra `porcentaje_libre` meta. Si `resultado_mes < 0`:
registrar el consumo en `reserva_movimiento`, calcular saldo y `meses_reserva_restantes =
saldo / deficit_mensual_esperado` a la ocupación actual. Alerta explícita si el saldo llega a
cero o menos.
**Hecho cuando:** tests cubren un mes positivo (brecha simple) y uno negativo (consumo, saldo,
meses restantes, alerta de reserva agotada).

### 8. (motor) Recuperación del capex
Recuperado acumulado contra `capex.monto` y ritmo esperado contra `horizonte_meses`.
Determinístico y genérico.
**Hecho cuando:** un test verifica el porcentaje recuperado dados N meses transcurridos y el
horizonte configurado.

### 9. (motor) Motor de recordatorios por fecha
`proxima_fecha` = `ultima_fecha` + `frecuencia_meses`, o `fecha_vencimiento_fija` si no hay
frecuencia. Clasifica vencido / próximo (ventana de `configuracion_dominio`) / al día. Las
categorías se leen de configuración, no son una lista fija en código.
**Hecho cuando:** un test con un recordatorio de seguro (por frecuencia) y uno de contrato
maestro (fecha fija) devuelve la clasificación correcta y el aviso antes del vencimiento.

### 10. (dominio) Diagnóstico del semáforo, determinístico (Paso 2)
Lee umbrales de `configuracion_dominio`.
`ocupacion_equilibrio = ceil((canon_maestro + gastos_fijos) / (arriendo_promedio_unidad × (1 − comision_pct)))`.
Semáforo de resultado: rojo si `resultado_mes < 0`; verde si `resultado_mes ≥ 0` y gasto
sobre ingreso ≤ `gasto_maximo_pct_verde`; amarillo en medio. Semáforo de ocupación: verde si
`ocupacion ≥ ocupacion_minima_verde` y `≥ ocupacion_equilibrio`; regla de vacancia → rojo si
la ocupación estuvo bajo el equilibrio durante `meses_consecutivos_baja_ocupacion_para_rojo`
meses seguidos. Explicación por estado con plantillas de texto, sin IA.
**Hecho cuando:** tests cubren los tres colores de cada semáforo y el disparo de la regla de
vacancia; cada explicación nombra la causa concreta.

### 11. (dominio) Módulo único de conocimiento fiscal colombiano
Un solo archivo identificable. Subarriendo como renta no laboral en cédula general:
deducibilidad del canon maestro y gastos asociados; tabla del art. 241 ET (0/19/28/33/35/37/39).
Produce `texto_fiscal` a partir de `resultado_mes` y `tarifa_marginal_actual`, o una nota
"sin cálculo de impuesto" si la casilla está desactivada. Excluye explícitamente el periodo
de remodelación. Toda salida incluye la advertencia de alcance.
**Hecho cuando:** se puede señalar el único archivo con lógica fiscal; un test verifica que el
texto siempre trae la advertencia y que respeta la casilla "no calcular impuesto".

### 12. (motor) Orquestación de la llamada a Anthropic
Definir la herramienta con `input_schema` y validar el payload antes de enviar. Ensambla el
contexto del mes: `resultado_mes`, brecha, estado de reserva, recuperación de capex, horizonte
del contrato, notas del activo y el `texto_fiscal` ya calculado por dominio. Si el API falla o
no hay crédito, el diagnóstico determinístico se muestra igual y la asesoría queda pendiente
de reintento.
**Hecho cuando:** con API simulada el payload valida contra el schema; con API caída la vista
del mes carga sin la asesoría y ofrece un botón de reintento.

### 13. (dominio) Generación del informe mensual de asesoría (Paso 5)
Prompt que produce: causa concreta de la brecha con su cifra, recomendación de reinversión, y
la nota fiscal integrada en prosa (el cálculo ya viene de la tarea 11). Guarda en
`asesoria_generada`.
**Hecho cuando:** una corrida real produce un texto que nombra una cifra y una causa
concretas y no cae en consejos genéricos.

### 14. Vista del mes (dashboard)
Reúne para el mes seleccionado: resultado en pesos, los dos semáforos con explicación,
ocupación real vs. equilibrio, brecha + estado de reserva + meses restantes, recuperación de
capex, recordatorios vencidos y próximos, y el informe de asesoría con su advertencia.
**Hecho cuando:** cargar un mes registrado muestra las siete piezas; un mes sin asesoría
generada muestra el resto y el botón de reintento.

### 15. Estado "primer mes / sin histórico"
La regla de vacancia y las tendencias se marcan "en espera" hasta tener suficientes meses, en
vez de mostrar un resultado en falso.
**Hecho cuando:** con un solo mes cargado la vista indica el estado en espera y la regla de
vacancia no se dispara.

### 16. README y datos iniciales del coliving
Instalación local, variable `ANTHROPIC_API_KEY`, comando para levantar, y un script que carga
el activo del coliving (5 unidades, comisión 10%, ubicación, notas) y sus umbrales como datos.
**Hecho cuando:** siguiendo el README desde cero, la app queda corriendo con el activo
precargado.

### 17. Recordatorio externo de carga mensual (decisión 9a)
No es código: el README documenta cómo crear un evento recurrente de calendario para cargar
el mes cuando llega el informe.
**Hecho cuando:** el README lo describe.

## Verificación end-to-end

1. Seguir el README desde cero: instalar, definir `ANTHROPIC_API_KEY`, correr el script de
   datos iniciales, levantar con `uvicorn`.
2. Completar la configuración: contrato maestro, política de distribución (probar que rechaza
   una suma ≠ 100), capex, tres recordatorios.
3. Registrar un mes "bueno" (4/5 unidades, resultado positivo) y cronometrar que toma menos
   de dos minutos. Verificar semáforos verdes, brecha, capex, recordatorios.
4. Registrar un mes "malo" (2/5 unidades, resultado negativo). Verificar semáforo rojo,
   consumo de reserva, meses de reserva restantes, y la alerta si la reserva se agota.
5. Generar el informe de asesoría y confirmar que nombra una cifra y una causa concretas y
   que todo cálculo tributario trae la advertencia de alcance.
6. Cortar la `ANTHROPIC_API_KEY` y registrar otro mes: el diagnóstico determinístico debe
   cargar igual y ofrecer reintentar la asesoría.
7. Correr la suite de tests de `motor/` y `dominio/`.
8. Buscar en el repo `5`, `10%` y el rango de arriendo: no deben aparecer en archivos de
   lógica. Confirmar que existe un único archivo con conocimiento fiscal.
9. Pasar a `verify-after-changes` cuando la implementación se dé por terminada.

## Regla del flujo durante la construcción

Si un error se repite mientras se construye, se corrige `spec.md`, no solo el código.
