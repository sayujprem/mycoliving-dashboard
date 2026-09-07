# MyColiving Dashboard

App web local, de un solo usuario, para diagnosticar cada mes el resultado de una operación
de subarriendo (coliving en modelo rent-to-rent). Toma el informe mensual de la inmobiliaria,
calcula un diagnóstico determinístico (resultado en pesos, ocupación real vs. de equilibrio,
semáforos, brecha vs. la meta de distribución, estado de la reserva, recuperación del capex),
avisa de vencimientos, y genera un informe mensual de asesoría financiera y fiscal.

Documentos de referencia: `spec.md`, `plan.md`, `evaluacion-negocio-producto.md`,
`ajustes-al-spec.md`.

## Requisitos

- Python 3.13
- Una API key de Anthropic **solo** para el informe de asesoría. El resto del dashboard
  (semáforo, brecha, reserva, capex, recordatorios) funciona sin ella.

## Instalación y arranque

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # y completar ANTHROPIC_API_KEY

python -m scripts.seed_coliving   # crea el activo del coliving y sus umbrales

uvicorn main:app --reload
```

Abrir http://127.0.0.1:8000

Variables de entorno (`.env`):

- `ANTHROPIC_API_KEY` — solo para el informe de asesoría.
- `ANTHROPIC_WORKSPACE_ID` — solo si tu API key está ligada a una identidad con workspaces
  (Anthropic devuelve un error 400 pidiéndolo). Se ve en la consola de Anthropic, formato
  `wrkspc_...`.
- `MYCOLIVING_MODELO` — opcional. Modelo para la asesoría (por defecto `claude-opus-5`).
- `MYCOLIVING_DB_PATH` — opcional. Ruta del archivo SQLite (por defecto `mycoliving.db`).

## Primeros pasos en la app

1. `python -m scripts.seed_coliving` deja el activo, los umbrales, el horizonte temporal y
   una política de distribución inicial (40 / 40 / 20).
2. En **Configuración** revisa los **umbrales y el horizonte** (ajustable en cualquier
   momento) y define el **capex** de zonas comunes y los **recordatorios** (seguro,
   mantenimiento, vencimientos).
3. **Esta operación no usa contrato maestro.** El canon que le pagas a la propietaria va
   dentro de los **gastos fijos** de cada informe mensual. Por eso `gasto_maximo_pct_verde`
   viene calibrado en **80** y no en 45: ese umbral mide
   `(comisión + gastos fijos + gastos variables) ÷ ingreso`, y con el canon adentro un mes
   sano ronda el 78–82%. Con el umbral en 45 el semáforo de resultado nunca podría ponerse
   verde.

   **Recalíbralo con tu primer mes real:** toma un mes bueno, calcula esa división y redondea
   hacia arriba. Si algún día separas el canon en un contrato maestro, bájalo a ~45.
4. Cuando llegue el informe de la inmobiliaria, entra a **Registrar mes** y copia los
   campos. El diagnóstico del mes aparece en el **Panel**.
5. En el Panel, botón **Generar asesoría** para el informe redactado (requiere la API key).

## Recordatorio mensual de carga

El dashboard corre en tu máquina y no te avisa solo, así que el aviso vive en el calendario.
Ya existe un **evento recurrente de calendario** creado para esto:

- **Título:** `Registrar el mes del coliving`
- **Cuándo:** el **día 5** de cada mes, 09:00–09:30 hora de Bogotá, con aviso 60 minutos antes.
- **Regla de recurrencia:** `RRULE:FREQ=MONTHLY;BYMONTHDAY=5`
- **Descripción:** los tres pasos (levantar el servidor, registrar el mes en
  `http://127.0.0.1:8000/registro` incluyendo el canon en los gastos fijos, y revisar el
  panel y generar la asesoría).

El día 5 es un supuesto sobre cuándo envía el informe la inmobiliaria. Si llega otro día,
mueve el evento **y también** el respaldo automático, que corre el mismo día a las 21:00
para alcanzar a incluir el mes recién registrado.

Si borras el evento por accidente, se recrea a mano en Google Calendar con los datos de
arriba.

## Respaldo mensual a Google Drive

La base es un solo archivo con años de historia financiera, así que se respalda sola el
**día 5 de cada mes a las 21:00** (después del recordatorio de las 09:00, para alcanzar a
incluir el mes recién registrado). Destino: la carpeta **Seguimiento estratégico** del Drive
de Nelson. Se conservan las 12 copias más recientes en Drive y las 3 más recientes en local.

### Instalación, una sola vez

```bash
mkdir -p ~/.local/bin && cd /tmp
curl -fsSLO https://downloads.rclone.org/rclone-current-osx-amd64.zip
unzip -oq rclone-current-osx-amd64.zip
cp rclone-*-osx-amd64/rclone ~/.local/bin/rclone && chmod +x ~/.local/bin/rclone
xattr -d com.apple.quarantine ~/.local/bin/rclone   # imprescindible: el binario no está firmado
rclone version
```

El `xattr` no es opcional. Sin él, Gatekeeper mata el binario en cuarentena y el respaldo
falla en silencio desde launchd, aunque funcione bien si lo corres tú en el terminal.

Luego el permiso de Drive:

```bash
rclone config
# n) New remote  →  name: gdrive  →  storage: drive
# client_id / client_secret: vacío   |   scope: 1 (full access)
# Edit advanced config: y  →  root_folder_id: 1Y_lZMYBc8-fCNTSmom5fseuBZy0RmORx
# Use auto config: y  →  se abre el navegador → autorizar
rclone lsd gdrive:     # debe listar el contenido de "Seguimiento estratégico"
```

Fijar `root_folder_id` es lo que hace que el respaldo escriba directamente en esa carpeta.

### Programarlo

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mycoliving.respaldo.plist
launchctl kickstart -k gui/$(id -u)/com.mycoliving.respaldo   # forzar una corrida ahora
```

### Comprobar que funciona

El resultado de la última corrida aparece en **Configuración → Último respaldo**, porque una
notificación de macOS se pierde y esa pantalla la miras cada mes. También queda en
`logs/respaldo.log`. Para correrlo a mano:

```bash
.venv/bin/python -m scripts.respaldo ; echo "exit=$?"   # 0 si todo bien, 2 si falló
```

Si el respaldo falla desde launchd pero funciona en el terminal, la causa casi siempre es una
de dos: falta el `xattr` de arriba, o macOS no le dio Acceso Total al Disco al Python de este
`.venv` (Preferencias del Sistema → Seguridad y Privacidad → Acceso Total al Disco).

## Estructura

- `motor/` — lógica independiente del tipo de activo y del país (resultado, brecha, reserva,
  capex, recordatorios por fecha, orquestación del API de Anthropic).
- `dominio/` — lógica específica del subarriendo de inmuebles y de Colombia (semáforo,
  conocimiento fiscal en `fiscal.py`, armado del contexto y del panel).
- `db/` — esquema SQLite (`schema.sql`), inicialización y repositorio de datos.
- `web/` — rutas FastAPI, plantillas Jinja2 y `static/app.css`.
- `scripts/` — datos de arranque.
- `tests/` — pruebas de `motor/`, `dominio/` y las rutas.

## Tests

```
pytest -q
```
