# MyColiving Dashboard

Plataforma web gratuita para diagnosticar cada mes el resultado de una operación de
subarriendo (coliving en modelo rent-to-rent). Toma el informe mensual de la inmobiliaria,
calcula un diagnóstico determinístico (resultado en pesos, ocupación real frente a la de
equilibrio, semáforos, brecha frente a la meta de distribución, estado de la reserva,
recuperación del capex), avisa de vencimientos y, en las cuentas que lo tienen habilitado,
genera un informe mensual de asesoría financiera y fiscal.

Cualquiera puede crear una cuenta y llevar el seguimiento de un activo.

## El problema que resuelve

En rent-to-rent el negocio es un *spread*: un canon fijo que se le paga a la propietaria
contra un recaudo variable que depende de cuántas unidades estén ocupadas. Cada mes llega el
informe de la inmobiliaria, se lee una vez y se archiva. Nadie dice si el mes fue bueno, y
cuando el spread se pone negativo uno se entera tres meses después, con la reserva ya
consumida.

La pieza central es la **ocupación de equilibrio**: cuántas unidades hay que tener
arrendadas para no poner plata ese mes. Ese número no aparece en ningún informe.

## Tres decisiones de diseño que vale la pena mirar

**El semáforo no lo decide un modelo de lenguaje.** El color sale de reglas determinísticas
y de umbrales que define el usuario, con la explicación armada por plantillas de texto. La
IA se usa en un solo punto —redactar la asesoría del mes— y si el API falla, el
diagnóstico se muestra igual. Un juicio financiero que cambia de opinión entre corridas no
sirve para decidir.

**Frontera `motor/` y `dominio/`.** `motor/` no sabe qué tipo de activo es ni en qué país
opera: trabaja con números (resultado del periodo, brecha, reserva, capex, fechas).
`dominio/` tiene lo que sí es específico: subarriendo de inmuebles y tributación colombiana,
con un único archivo (`dominio/fiscal.py`) que concentra todo el conocimiento fiscal.

**El aislamiento entre cuentas vive en dos capas.** La aplicación solo consulta por el
`activo_id` que resuelve la sesión, nunca por uno que venga del navegador. Y la base de datos
aplica *Row Level Security* (RLS: políticas que filtran filas según quién consulta): cada
transacción declara su dueño con `SET LOCAL`, y Postgres niega cualquier fila ajena aunque el
código la pida por error. `tests/test_aislamiento.py` intenta la fuga por nueve caminos
distintos en cada cambio.

## Stack y costo

| Pieza | Servicio | Costo |
|---|---|---|
| Aplicación (FastAPI + Jinja2) | Vercel, plan Hobby | $0 |
| Base de datos (PostgreSQL 17) | Supabase, plan Free | $0 |
| Correo de verificación | API de Gmail | $0 hasta ~500/día |
| Respaldo y mantenimiento | GitHub Actions | $0 en repos públicos |
| Asesoría con IA | API de Anthropic, `claude-sonnet-5` | ~0,05 USD por informe |

Sin frameworks de JavaScript: el único script es `web/static/app.js`, con dos
comportamientos pequeños.

> **Licencia de Vercel.** El plan Hobby prohíbe el uso comercial, que Vercel define como
> cualquier despliegue del que alguien obtenga beneficio económico. Si la plataforma empieza
> a cobrar o a servir de vitrina para un negocio, hay que pasar a Pro.

## Desarrollo local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

scripts/pg_local.sh start          # PostgreSQL 17 local, sin Docker ni Homebrew
cp .env.example .env               # y completar según los comentarios
python -m db.init_db

uvicorn main:app --reload
```

Abrir http://127.0.0.1:8000 y crear una cuenta. Sin `GMAIL_OAUTH`, el enlace de
verificación no se envía: aparece en la terminal donde corre uvicorn.

`scripts/pg_local.sh` descarga los binarios oficiales de PostgreSQL a `.pg/` (ignorada por
git). Nada se instala en el sistema; borrar esa carpeta lo deshace todo.

### Datos de ejemplo

```bash
python -m scripts.demo cargar --email tu@correo.com
```

Carga en esa cuenta seis meses que van de verde a rojo, agotan el fondo de reserva y
disparan la regla de vacancia, más capex y recordatorios en sus tres estados. El panel avisa
que son datos de ejemplo; se quitan con `python -m scripts.demo limpiar --email ...` o con
el botón del banner.

## Despliegue

Una sola vez:

1. **Supabase.** Crear un proyecto y **apagar la Data API** (*Project Settings → Data
   API*). Supabase publica por HTTP el esquema `public` con una clave que es pública por
   diseño; la aplicación no la usa y el esquema ya le retira todos los permisos a esos
   roles, pero apagarla cierra la puerta entera. De *Connect* copiar dos cadenas: la del
   **transaction pooler** (puerto 6543), que usa la aplicación, y la del **session pooler**
   (puerto 5432), que usan el respaldo y el mantenimiento. `pg_dump` no funciona por el
   transaction pooler.
2. **Esquema.** `DATABASE_URL=<session pooler> python -m db.init_db`. Es idempotente: se
   puede volver a correr tras cada cambio del esquema.
3. **Correo.** La aplicación envía por la API de Gmail con un permiso OAuth, no por SMTP
   con contraseña: Google bloquea como sospechoso el inicio de sesión por SMTP de una
   cuenta nueva desde servidores en la nube. En Google Cloud, habilitar la **Gmail API**,
   agregar el permiso `gmail.send`, publicar la app y crear un cliente OAuth de tipo
   **App de escritorio**. Con su JSON descargado:
   `python -m scripts.autorizar_gmail --credenciales ~/Downloads/client_secret_….json`.
   El script pide la autorización, envía un correo de prueba y deja `GMAIL_OAUTH` en el
   portapapeles. Si algún día Google revoca el permiso (por ejemplo, al cambiar la
   contraseña de la cuenta), el registro de Vercel lo dice y basta con volver a correrlo.
4. **Anthropic.** Crear una API key exclusiva para producción y fijar un **tope de gasto
   mensual** en la consola (*Settings → Limits*). Con la asesoría habilitada cuenta por
   cuenta, 5 USD al mes alcanzan para unos 100 informes.
5. **Vercel.** Importar el repositorio. Detecta FastAPI solo; `vercel.json` fija la
   duración máxima de la función y excluye del paquete lo que no se usa en producción.
   Variables de entorno:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | transaction pooler de Supabase (puerto 6543) |
   | `SESSION_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `MYCOLIVING_ENTORNO` | `produccion` (activa la cookie `Secure` y HSTS) |
   | `APP_URL` | la URL pública, sin barra final |
   | `GMAIL_OAUTH` | el que genera `scripts/autorizar_gmail.py` |
   | `ANTHROPIC_API_KEY` | la de producción |
   | `ANTHROPIC_WORKSPACE_ID` | solo si la key pertenece a un workspace |

6. **Tus datos.** Migrar la base de la versión de un solo usuario a tu cuenta (ver abajo).
7. **GitHub.** Configurar los secretos del respaldo (ver abajo).

### Migrar los datos de la versión anterior

```bash
DATABASE_URL=<session pooler> python -m scripts.migrar_a_postgres \
    --sqlite mycoliving.db --email tu@correo.com
```

Crea la cuenta verificada y como administradora si no existe (pide la contraseña por
teclado), y copia las diez tablas en una sola transacción. Si los conteos no cuadran tabla
por tabla, deshace todo. Abre el SQLite en modo solo lectura: el archivo original no se toca.
Se niega a correr sobre una cuenta que ya tiene un activo.

### Administración

La asesoría con IA gasta crédito del API, así que nace apagada en cada cuenta nueva. Desde
**/admin** (visible solo para cuentas administradoras) se ve la lista de cuentas, cuántos
informes ha generado cada una, y se enciende o apaga la asesoría.

## Primeros pasos en la app

1. Crear la cuenta, confirmar el correo y definir el activo.
2. En **Configuración** revisar los **umbrales y el horizonte** (ajustables en cualquier
   momento) y definir el **capex** de zonas comunes y los **recordatorios** (seguro,
   mantenimiento, vencimientos).
3. **Si la operación no usa contrato maestro**, el canon que se le paga a la propietaria va
   dentro de los **gastos fijos** de cada informe mensual. En ese caso
   `gasto_maximo_pct_verde` tiene que calibrarse cerca de **80** y no en 45: ese umbral mide
   `(comisión + gastos fijos + gastos variables) ÷ ingreso`, y con el canon adentro un mes
   sano ronda el 78–82%. Con el umbral en 45 el semáforo de resultado nunca podría ponerse
   verde.

   **Recalíbralo con tu primer mes real.** No hace falta calcular nada a mano: la app ya te
   da el número. En el Panel, la explicación bajo el semáforo de resultado dice *"los gastos
   y la comisión consumieron **79%** del ingreso"*. Toma ese porcentaje de un mes normal o
   bueno, súmale 2 o 3 puntos de margen, y ese es el umbral (79% → 82).

   El margen importa: puesto justo en el borde, cualquier mes con un gasto imprevisto se
   pone amarillo y el semáforo deja de informar; puesto muy alto, nunca se pone amarillo y
   tampoco informa. Si un mes dio pérdida, el panel no muestra el porcentaje: usa otro mes.

   Si la operación separa el canon en un contrato maestro, el umbral va en ~45.
4. Cuando llegue el informe de la inmobiliaria, entrar a **Registrar mes** y copiar los
   campos. El diagnóstico aparece en el **Panel**.

## Recordatorio mensual de carga

La plataforma no manda avisos para registrar el mes. Lo que funciona es un
evento recurrente de calendario el día que suele llegar el informe de la inmobiliaria, con
el enlace directo a `/registro` en la descripción. Por ejemplo, con la regla
`RRULE:FREQ=MONTHLY;BYMONTHDAY=5`, a las 09:00 y con aviso una hora antes.

## Respaldo mensual

El día 5 de cada mes, `.github/workflows/respaldo.yml` vuelca la base con `pg_dump`, la
cifra con `gpg` (AES-256) y la sube a Google Drive con `rclone`. Después verifica que el
archivo esté en el destino y que pese lo mismo que el local, porque un `rclone copy` puede
devolver 0 sin haber subido nada. Conserva las 12 copias más recientes.

**La copia sale siempre cifrada.** Contiene los datos de todas las cuentas. Sin la clave de
cifrado configurada, el respaldo falla; nunca sube en claro.

Secretos del repositorio (*Settings → Secrets and variables → Actions*):

| Secreto | Contenido |
|---|---|
| `DATABASE_URL_RESPALDO` | session pooler de Supabase (puerto 5432) |
| `RESPALDO_CLAVE` | frase de cifrado larga. **Guárdala también fuera de GitHub**: sin ella, ninguna copia se puede leer |
| `RCLONE_CONF` | solo la sección `[respaldos]` de `~/.config/rclone/rclone.conf` |

Para correrlo a mano: pestaña **Actions → Respaldo mensual → Run workflow**.

### Restaurar una copia

```bash
gpg --decrypt mycoliving-AAAA-MM-DD.dump.gpg > copia.dump
pg_restore --no-owner --clean --if-exists -d "$DATABASE_URL_RESPALDO" copia.dump
```

### El permiso de Drive para rclone

`RCLONE_CONF` guarda un permiso OAuth de Google para un remoto de rclone llamado
`respaldos`. Dos condiciones:

- **Identificador de cliente propio, con la app publicada.** El compartido de rclone deja de
  funcionar durante 2026, y una app de Google en modo *Prueba* hace caducar el permiso a los
  7 días: el respaldo mensual fallaría siempre.
- **Permiso `drive.file`** (opción 3 en `rclone config`), no `drive`. Con él rclone solo ve
  los archivos que él mismo crea. Si el secreto se filtrara, expondría únicamente los
  respaldos cifrados, no el resto del Drive. Además es un permiso no sensible: Google no
  exige verificar la app ni muestra la advertencia de app no verificada.

Los respaldos quedan en la carpeta `mycoliving` que rclone crea en tu Drive
(`RESPALDO_REMOTO`, por defecto `respaldos:mycoliving/`). La guía paso a paso está en
`OUTPUTS/mycoliving_dashboard/` del espacio de trabajo.

### Mantenimiento de la base

`.github/workflows/mantenimiento.yml` corre cada cuatro días. Evita que Supabase pause la
base (el plan Free la pausa tras 7 días sin consultas, y despertarla tarda ~30 segundos) y
borra los registros de intentos de acceso de más de un día, que la política de privacidad
promete no conservar más de 7.

> **GitHub desactiva los flujos programados de un repositorio público tras 60 días sin
> commits.** Manda un correo antes de hacerlo. Si llega, se reactivan desde la pestaña
> Actions; si no, el respaldo deja de correr sin más aviso.

## Estructura

- `motor/` — lógica independiente del tipo de activo y del país (resultado, brecha, reserva,
  capex, recordatorios por fecha, orquestación del API de Anthropic).
- `dominio/` — lógica específica del subarriendo de inmuebles y de Colombia (semáforo,
  conocimiento fiscal en `fiscal.py`, armado del contexto y del panel).
- `db/` — esquema PostgreSQL con sus políticas de aislamiento (`schema.sql`), conexión,
  repositorio de datos y cuentas (`usuarios.py`).
- `web/` — rutas FastAPI, sesión y CSRF (`auth.py`), cabeceras de seguridad, correo,
  plantillas Jinja2 y `static/`.
- `scripts/` — base local, datos de ejemplo, migración y respaldo.
- `tests/` — pruebas de `motor/`, `dominio/`, las rutas, las cuentas y el aislamiento.

## Pruebas

```bash
scripts/pg_local.sh start
pytest -q
```

Corren contra la base `mycoliving_test`. `tests/conftest.py` se niega a arrancar si la base
de pruebas no lleva `test` en el nombre: las pruebas borran todas las tablas y no pueden
correr por descuido contra producción. `.github/workflows/pruebas.yml` corre la suite
completa en cada push.
