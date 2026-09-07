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
3. El **contrato maestro es opcional**. Si no lo defines, incluye el canon que le pagas a
   la propietaria dentro de los gastos fijos de cada informe mensual; si lo defines, el
   sistema lo descuenta aparte del resultado.
4. Cuando llegue el informe de la inmobiliaria, entra a **Registrar mes** y copia los
   campos. El diagnóstico del mes aparece en el **Panel**.
5. En el Panel, botón **Generar asesoría** para el informe redactado (requiere la API key).

## Recordatorio mensual de carga

El dashboard corre en tu máquina y no te avisa solo. Para no depender de la memoria, crea un
**evento recurrente de calendario**:

- Frecuencia: mensual, el día en que la inmobiliaria suele enviar el informe.
- Título: "Registrar el mes del coliving".
- Descripción / enlace: `http://127.0.0.1:8000/registro`.

Al llegar el aviso: abrir el enlace, copiar el informe, revisar el Panel y generar la
asesoría del mes.

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
