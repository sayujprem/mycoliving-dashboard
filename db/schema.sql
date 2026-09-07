-- Esquema de MyColiving Dashboard.
-- Todas las tablas de datos llevan activo_id, aunque hoy solo exista un activo.
-- Fechas en texto ISO 8601 ('YYYY-MM-DD'). Dinero y porcentajes en REAL.

CREATE TABLE IF NOT EXISTS activo (
    id                          INTEGER PRIMARY KEY,
    nombre                      TEXT    NOT NULL,
    tipo                        TEXT    NOT NULL,
    unidades_totales            INTEGER NOT NULL CHECK (unidades_totales > 0),
    comision_administrador_pct  REAL    NOT NULL CHECK (comision_administrador_pct >= 0 AND comision_administrador_pct <= 100),
    moneda                      TEXT    NOT NULL DEFAULT 'COP',
    ubicacion                   TEXT,
    notas                       TEXT
);

-- Reemplaza al 'horizonte_patrimonial' del spec original. El activo no es propio:
-- lo que importa es el contrato maestro de arriendo con la propietaria.
CREATE TABLE IF NOT EXISTS contrato_maestro (
    id                     INTEGER PRIMARY KEY,
    activo_id              INTEGER NOT NULL REFERENCES activo(id),
    canon_mensual          REAL    NOT NULL CHECK (canon_mensual >= 0),
    fecha_inicio           TEXT    NOT NULL,
    fecha_vencimiento      TEXT    NOT NULL,
    vigencia_meses         INTEGER NOT NULL CHECK (vigencia_meses > 0),
    regla_reajuste         TEXT,
    ventana_preaviso_dias  INTEGER NOT NULL DEFAULT 0 CHECK (ventana_preaviso_dias >= 0),
    fecha_definicion       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS politica_distribucion (
    id                     INTEGER PRIMARY KEY,
    activo_id              INTEGER NOT NULL REFERENCES activo(id),
    porcentaje_libre       REAL    NOT NULL CHECK (porcentaje_libre >= 0 AND porcentaje_libre <= 100),
    porcentaje_reinversion REAL    NOT NULL CHECK (porcentaje_reinversion >= 0 AND porcentaje_reinversion <= 100),
    porcentaje_reserva     REAL    NOT NULL CHECK (porcentaje_reserva >= 0 AND porcentaje_reserva <= 100),
    tarifa_marginal_actual REAL    NOT NULL DEFAULT 0 CHECK (tarifa_marginal_actual >= 0 AND tarifa_marginal_actual <= 39),
    calcular_impuesto      INTEGER NOT NULL DEFAULT 1 CHECK (calcular_impuesto IN (0, 1)),
    fecha_definicion       TEXT    NOT NULL,
    -- Backstop de la validacion de la tarea 4; el mensaje al usuario lo da la app.
    CHECK (abs(porcentaje_libre + porcentaje_reinversion + porcentaje_reserva - 100) < 0.01)
);

-- Umbrales de "que es optimo". Editables sin tocar codigo.
CREATE TABLE IF NOT EXISTS configuracion_dominio (
    id          INTEGER PRIMARY KEY,
    activo_id   INTEGER NOT NULL REFERENCES activo(id),
    clave       TEXT    NOT NULL,
    valor       TEXT    NOT NULL,
    descripcion TEXT,
    UNIQUE (activo_id, clave)
);

-- Inversion de montaje (zonas comunes). Se recupera contra la vigencia del contrato.
CREATE TABLE IF NOT EXISTS capex (
    id              INTEGER PRIMARY KEY,
    activo_id       INTEGER NOT NULL REFERENCES activo(id),
    concepto        TEXT    NOT NULL,
    monto           REAL    NOT NULL CHECK (monto >= 0),
    fecha           TEXT    NOT NULL,
    horizonte_meses INTEGER NOT NULL CHECK (horizonte_meses > 0)
);

CREATE TABLE IF NOT EXISTS recordatorios (
    id                     INTEGER PRIMARY KEY,
    activo_id              INTEGER NOT NULL REFERENCES activo(id),
    categoria              TEXT    NOT NULL,
    descripcion            TEXT    NOT NULL,
    ultima_fecha           TEXT,
    frecuencia_meses       INTEGER CHECK (frecuencia_meses IS NULL OR frecuencia_meses > 0),
    fecha_vencimiento_fija TEXT,
    proxima_fecha          TEXT,
    -- O es periodico (frecuencia) o tiene fecha fija de vencimiento.
    CHECK (frecuencia_meses IS NOT NULL OR fecha_vencimiento_fija IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS reporte_mensual (
    id               INTEGER PRIMARY KEY,
    activo_id        INTEGER NOT NULL REFERENCES activo(id),
    mes              INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio             INTEGER NOT NULL CHECK (anio >= 2000),
    gastos_fijos     REAL    NOT NULL DEFAULT 0 CHECK (gastos_fijos >= 0),
    gastos_variables REAL    NOT NULL DEFAULT 0 CHECK (gastos_variables >= 0),
    comision_admin   REAL    NOT NULL DEFAULT 0 CHECK (comision_admin >= 0),
    novedades        TEXT,
    fecha_registro   TEXT    NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

-- Una fila por unidad del mes. ocupacion = conteo de arrendada = 1;
-- ingreso_subarriendo = suma de ingreso_inquilino.
CREATE TABLE IF NOT EXISTS reporte_unidad (
    id                 INTEGER PRIMARY KEY,
    reporte_mensual_id INTEGER NOT NULL REFERENCES reporte_mensual(id) ON DELETE CASCADE,
    unidad_label       TEXT    NOT NULL,
    arrendada          INTEGER NOT NULL DEFAULT 0 CHECK (arrendada IN (0, 1)),
    ingreso_inquilino  REAL    NOT NULL DEFAULT 0 CHECK (ingreso_inquilino >= 0),
    UNIQUE (reporte_mensual_id, unidad_label)
);

CREATE TABLE IF NOT EXISTS reserva_movimiento (
    id               INTEGER PRIMARY KEY,
    activo_id        INTEGER NOT NULL REFERENCES activo(id),
    mes              INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio             INTEGER NOT NULL CHECK (anio >= 2000),
    monto            REAL    NOT NULL,
    saldo_resultante REAL    NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

CREATE TABLE IF NOT EXISTS asesoria_generada (
    id                    INTEGER PRIMARY KEY,
    activo_id             INTEGER NOT NULL REFERENCES activo(id),
    mes                   INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio                  INTEGER NOT NULL CHECK (anio >= 2000),
    semaforo_resultado    TEXT    CHECK (semaforo_resultado IS NULL OR semaforo_resultado IN ('verde', 'amarillo', 'rojo')),
    semaforo_ocupacion    TEXT    CHECK (semaforo_ocupacion IS NULL OR semaforo_ocupacion IN ('verde', 'amarillo', 'rojo')),
    resultado_mes         REAL,
    ocupacion_equilibrio  REAL,
    porcentaje_libre_real REAL,
    brecha_frente_a_meta  REAL,
    capex_recuperado_pct  REAL,
    texto_asesoria        TEXT,
    texto_fiscal          TEXT,
    fecha_generacion      TEXT    NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

-- La ocupacion del mes no puede superar las unidades del activo.
CREATE TRIGGER IF NOT EXISTS trg_reporte_unidad_ocupacion_insert
BEFORE INSERT ON reporte_unidad
WHEN NEW.arrendada = 1
BEGIN
    SELECT RAISE(ABORT, 'La ocupacion del mes supera las unidades del activo')
    WHERE (
        SELECT COUNT(*) FROM reporte_unidad
        WHERE reporte_mensual_id = NEW.reporte_mensual_id AND arrendada = 1
    ) + 1 > (
        SELECT a.unidades_totales
        FROM reporte_mensual rm JOIN activo a ON a.id = rm.activo_id
        WHERE rm.id = NEW.reporte_mensual_id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_reporte_unidad_ocupacion_update
BEFORE UPDATE ON reporte_unidad
WHEN NEW.arrendada = 1
BEGIN
    SELECT RAISE(ABORT, 'La ocupacion del mes supera las unidades del activo')
    WHERE (
        SELECT COUNT(*) FROM reporte_unidad
        WHERE reporte_mensual_id = NEW.reporte_mensual_id AND arrendada = 1 AND id <> NEW.id
    ) + 1 > (
        SELECT a.unidades_totales
        FROM reporte_mensual rm JOIN activo a ON a.id = rm.activo_id
        WHERE rm.id = NEW.reporte_mensual_id
    );
END;
