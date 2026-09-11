-- Esquema de MyColiving Dashboard (PostgreSQL).
--
-- La raiz del grafo es `usuario`. Cada cuenta tiene como maximo un activo, y todo
-- dato de negocio cuelga de ese activo. El borrado de una cuenta arrastra en cascada
-- absolutamente todo su rastro.
--
-- Convenciones:
--   - Dinero y saldos en NUMERIC(14,2); porcentajes en NUMERIC(6,3). Nunca punto flotante.
--   - Fechas de calendario en DATE; marcas de tiempo del sistema en TIMESTAMPTZ.
--   - Los identificadores son BIGINT GENERATED ALWAYS AS IDENTITY.
--   - Toda funcion fija `SET search_path = public, pg_temp`. Sin eso, busca tablas y
--     funciones en el search_path de quien la llama, y un objeto con el mismo nombre en
--     otro esquema podria suplantar al nuestro. app_usuario_id() sostiene todas las
--     politicas de aislamiento: no puede depender de eso. pg_temp va al final para
--     que tampoco se pueda suplantar nada desde el esquema temporal de la sesion.
--
-- El aislamiento entre cuentas se defiende en dos capas: la aplicacion filtra por
-- activo_id (resuelto desde la sesion, nunca desde el cliente) y la base aplica RLS
-- sobre app.usuario_id. Ver la seccion "Aislamiento" al final del archivo.


-- ---------------------------------------------------------------------------
-- Cuentas y autenticacion
-- ---------------------------------------------------------------------------

-- El correo se normaliza a minusculas en la aplicacion; el CHECK lo hace explicito
-- para que un INSERT fuera de la app no pueda crear duplicados por diferencia de caja.
CREATE TABLE IF NOT EXISTS usuario (
    id                  BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email               TEXT        NOT NULL UNIQUE
                                    CHECK (email = lower(email) AND position('@' IN email) > 1),
    password_hash       TEXT        NOT NULL,
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    email_verificado_en TIMESTAMPTZ,
    -- La asesoria con IA gasta credito del API, asi que nace apagada y se habilita
    -- cuenta por cuenta desde /admin.
    asesoria_habilitada BOOLEAN     NOT NULL DEFAULT false,
    es_admin            BOOLEAN     NOT NULL DEFAULT false,
    -- Contador de invalidacion de sesiones: al cambiar la contrasena se incrementa y
    -- toda cookie emitida antes deja de servir, sin necesidad de una tabla de sesiones.
    token_sesion        INTEGER     NOT NULL DEFAULT 1
);

-- Se guarda el hash del token, nunca el token en claro: si alguien lee esta tabla
-- no puede verificar cuentas ni restablecer contrasenas ajenas.
CREATE TABLE IF NOT EXISTS token_email (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT      NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo       TEXT        NOT NULL CHECK (tipo IN ('verificacion', 'recuperacion')),
    hash_token TEXT        NOT NULL UNIQUE,
    expira_en  TIMESTAMPTZ NOT NULL,
    usado_en   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_token_email_usuario ON token_email (usuario_id, tipo);

-- Ventana deslizante para frenar fuerza bruta sin depender de Redis ni de un servicio
-- externo. Se purga sola: ver limpiar_intentos_viejos() mas abajo.
-- `tipo` separa los tres flujos que se limitan: iniciar sesion, crear cuenta y pedir
-- un enlace de recuperacion. Cada uno tiene su propio tope.
CREATE TABLE IF NOT EXISTS intento_acceso (
    id      BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo    TEXT        NOT NULL DEFAULT 'acceso'
                        CHECK (tipo IN ('acceso', 'alta', 'recuperacion', 'reenvio')),
    email   TEXT,
    ip      TEXT,
    exitoso BOOLEAN     NOT NULL DEFAULT false,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_intento_email ON intento_acceso (tipo, email, ts DESC);
CREATE INDEX IF NOT EXISTS ix_intento_ip    ON intento_acceso (tipo, ip, ts DESC);

-- Auditoria de gasto del API de Anthropic, independiente de la consola del proveedor.
CREATE TABLE IF NOT EXISTS uso_asesoria (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id BIGINT      NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    anio       INTEGER     NOT NULL,
    mes        INTEGER     NOT NULL CHECK (mes BETWEEN 1 AND 12),
    ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_uso_asesoria_usuario ON uso_asesoria (usuario_id, ts DESC);


-- ---------------------------------------------------------------------------
-- El activo y sus datos de negocio
-- ---------------------------------------------------------------------------

-- UNIQUE sobre usuario_id impone la regla "un activo por cuenta" en la base, no solo
-- en la aplicacion. Quitar ese UNIQUE es todo lo que hace falta para permitir varios.
CREATE TABLE IF NOT EXISTS activo (
    id                          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id                  BIGINT       NOT NULL UNIQUE REFERENCES usuario(id) ON DELETE CASCADE,
    nombre                      TEXT         NOT NULL,
    tipo                        TEXT         NOT NULL,
    unidades_totales            INTEGER      NOT NULL CHECK (unidades_totales > 0),
    comision_administrador_pct  NUMERIC(6,3) NOT NULL CHECK (comision_administrador_pct >= 0 AND comision_administrador_pct <= 100),
    moneda                      TEXT         NOT NULL DEFAULT 'COP',
    ubicacion                   TEXT,
    notas                       TEXT
);

-- Reemplaza al 'horizonte_patrimonial' del spec original. El activo no es propio:
-- lo que importa es el contrato maestro de arriendo con la propietaria.
-- Tabla versionada: se acumulan filas y vale la ultima por id.
CREATE TABLE IF NOT EXISTS contrato_maestro (
    id                     BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id              BIGINT        NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    canon_mensual          NUMERIC(14,2) NOT NULL CHECK (canon_mensual >= 0),
    fecha_inicio           DATE          NOT NULL,
    fecha_vencimiento      DATE          NOT NULL,
    vigencia_meses         INTEGER       NOT NULL CHECK (vigencia_meses > 0),
    regla_reajuste         TEXT,
    ventana_preaviso_dias  INTEGER       NOT NULL DEFAULT 0 CHECK (ventana_preaviso_dias >= 0),
    fecha_definicion       DATE          NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_contrato_activo ON contrato_maestro (activo_id, id DESC);

-- Tambien versionada.
CREATE TABLE IF NOT EXISTS politica_distribucion (
    id                     BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id              BIGINT       NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    porcentaje_libre       NUMERIC(6,3) NOT NULL CHECK (porcentaje_libre >= 0 AND porcentaje_libre <= 100),
    porcentaje_reinversion NUMERIC(6,3) NOT NULL CHECK (porcentaje_reinversion >= 0 AND porcentaje_reinversion <= 100),
    porcentaje_reserva     NUMERIC(6,3) NOT NULL CHECK (porcentaje_reserva >= 0 AND porcentaje_reserva <= 100),
    tarifa_marginal_actual NUMERIC(6,3) NOT NULL DEFAULT 0 CHECK (tarifa_marginal_actual >= 0 AND tarifa_marginal_actual <= 39),
    calcular_impuesto      BOOLEAN      NOT NULL DEFAULT true,
    fecha_definicion       DATE         NOT NULL,
    -- Backstop de la validacion de la tarea 4; el mensaje al usuario lo da la app.
    -- Se conserva la tolerancia de 0.01 por los datos migrados desde SQLite.
    CHECK (abs(porcentaje_libre + porcentaje_reinversion + porcentaje_reserva - 100) < 0.01)
);

CREATE INDEX IF NOT EXISTS ix_politica_activo ON politica_distribucion (activo_id, id DESC);

-- Umbrales de "que es optimo". Editables sin tocar codigo.
CREATE TABLE IF NOT EXISTS configuracion_dominio (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id   BIGINT NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    clave       TEXT   NOT NULL,
    valor       TEXT   NOT NULL,
    descripcion TEXT,
    UNIQUE (activo_id, clave)
);

-- Inversion de montaje (zonas comunes). Se recupera contra la vigencia del contrato.
CREATE TABLE IF NOT EXISTS capex (
    id              BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id       BIGINT        NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    concepto        TEXT          NOT NULL,
    monto           NUMERIC(14,2) NOT NULL CHECK (monto >= 0),
    fecha           DATE          NOT NULL,
    horizonte_meses INTEGER       NOT NULL CHECK (horizonte_meses > 0)
);

CREATE INDEX IF NOT EXISTS ix_capex_activo ON capex (activo_id, fecha DESC, id DESC);

CREATE TABLE IF NOT EXISTS recordatorios (
    id                     BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id              BIGINT  NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    categoria              TEXT    NOT NULL,
    descripcion            TEXT    NOT NULL,
    ultima_fecha           DATE,
    frecuencia_meses       INTEGER CHECK (frecuencia_meses IS NULL OR frecuencia_meses > 0),
    fecha_vencimiento_fija DATE,
    proxima_fecha          DATE,
    -- O es periodico (frecuencia) o tiene fecha fija de vencimiento.
    CHECK (frecuencia_meses IS NOT NULL OR fecha_vencimiento_fija IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_recordatorios_activo ON recordatorios (activo_id, proxima_fecha);

CREATE TABLE IF NOT EXISTS reporte_mensual (
    id               BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id        BIGINT        NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    mes              INTEGER       NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio             INTEGER       NOT NULL CHECK (anio >= 2000),
    gastos_fijos     NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (gastos_fijos >= 0),
    gastos_variables NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (gastos_variables >= 0),
    comision_admin   NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (comision_admin >= 0),
    novedades        TEXT,
    fecha_registro   DATE          NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS ix_reporte_activo ON reporte_mensual (activo_id, anio DESC, mes DESC);

-- Una fila por unidad del mes. ocupacion = conteo de arrendada = true;
-- ingreso_subarriendo = suma de ingreso_inquilino.
CREATE TABLE IF NOT EXISTS reporte_unidad (
    id                 BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reporte_mensual_id BIGINT        NOT NULL REFERENCES reporte_mensual(id) ON DELETE CASCADE,
    unidad_label       TEXT          NOT NULL,
    arrendada          BOOLEAN       NOT NULL DEFAULT false,
    ingreso_inquilino  NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (ingreso_inquilino >= 0),
    UNIQUE (reporte_mensual_id, unidad_label)
);

CREATE INDEX IF NOT EXISTS ix_unidad_reporte ON reporte_unidad (reporte_mensual_id);

-- Tabla derivada: se reconstruye entera con dominio.reserva.recalcular_reserva.
CREATE TABLE IF NOT EXISTS reserva_movimiento (
    id               BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id        BIGINT        NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    mes              INTEGER       NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio             INTEGER       NOT NULL CHECK (anio >= 2000),
    monto            NUMERIC(14,2) NOT NULL,
    saldo_resultante NUMERIC(14,2) NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS ix_reserva_activo ON reserva_movimiento (activo_id, anio, mes);

CREATE TABLE IF NOT EXISTS asesoria_generada (
    id                    BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    activo_id             BIGINT        NOT NULL REFERENCES activo(id) ON DELETE CASCADE,
    mes                   INTEGER       NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio                  INTEGER       NOT NULL CHECK (anio >= 2000),
    semaforo_resultado    TEXT          CHECK (semaforo_resultado IS NULL OR semaforo_resultado IN ('verde', 'amarillo', 'rojo')),
    semaforo_ocupacion    TEXT          CHECK (semaforo_ocupacion IS NULL OR semaforo_ocupacion IN ('verde', 'amarillo', 'rojo')),
    resultado_mes         NUMERIC(14,2),
    ocupacion_equilibrio  NUMERIC(10,4),
    porcentaje_libre_real NUMERIC(10,4),
    brecha_frente_a_meta  NUMERIC(14,2),
    capex_recuperado_pct  NUMERIC(10,4),
    texto_asesoria        TEXT,
    texto_fiscal          TEXT,
    fecha_generacion      DATE          NOT NULL,
    UNIQUE (activo_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS ix_asesoria_activo ON asesoria_generada (activo_id, anio DESC, mes DESC);


-- ---------------------------------------------------------------------------
-- Regla de ocupacion
-- ---------------------------------------------------------------------------

-- La ocupacion del mes no puede superar las unidades del activo.
-- En SQLite esto eran dos triggers con RAISE(ABORT); en Postgres, una funcion
-- PL/pgSQL compartida por ambos. La regla de negocio es identica.
CREATE OR REPLACE FUNCTION fn_valida_ocupacion() RETURNS TRIGGER AS $$
DECLARE
    arrendadas INTEGER;
    tope       INTEGER;
BEGIN
    IF NOT NEW.arrendada THEN
        RETURN NEW;
    END IF;

    SELECT count(*) INTO arrendadas
    FROM reporte_unidad
    WHERE reporte_mensual_id = NEW.reporte_mensual_id
      AND arrendada
      AND id IS DISTINCT FROM NEW.id;

    SELECT a.unidades_totales INTO tope
    FROM reporte_mensual rm
    JOIN activo a ON a.id = rm.activo_id
    WHERE rm.id = NEW.reporte_mensual_id;

    IF arrendadas + 1 > tope THEN
        RAISE EXCEPTION 'La ocupacion del mes supera las unidades del activo';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public, pg_temp;

DROP TRIGGER IF EXISTS trg_reporte_unidad_ocupacion_insert ON reporte_unidad;
CREATE TRIGGER trg_reporte_unidad_ocupacion_insert
    BEFORE INSERT ON reporte_unidad
    FOR EACH ROW EXECUTE FUNCTION fn_valida_ocupacion();

DROP TRIGGER IF EXISTS trg_reporte_unidad_ocupacion_update ON reporte_unidad;
CREATE TRIGGER trg_reporte_unidad_ocupacion_update
    BEFORE UPDATE ON reporte_unidad
    FOR EACH ROW EXECUTE FUNCTION fn_valida_ocupacion();


-- ---------------------------------------------------------------------------
-- Mantenimiento
-- ---------------------------------------------------------------------------

-- Los intentos de acceso solo sirven dentro de la ventana deslizante; mas alla de
-- un dia son datos personales (IP, correo) que no hay razon para conservar.
CREATE OR REPLACE FUNCTION limpiar_intentos_viejos() RETURNS void AS $$
BEGIN
    DELETE FROM intento_acceso WHERE ts < now() - INTERVAL '1 day';
    DELETE FROM token_email    WHERE expira_en < now() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql SET search_path = public, pg_temp;


-- ---------------------------------------------------------------------------
-- Aislamiento (Row Level Security)
-- ---------------------------------------------------------------------------

-- Segunda capa de defensa. La aplicacion ya filtra por activo_id, pero si algun dia
-- se escapa un WHERE, la base rechaza la fila igual.
--
-- Como funciona: la aplicacion abre cada transaccion con
--     SET LOCAL ROLE mycoliving_app;
--     SET LOCAL app.usuario_id = '<id>';
-- El rol mycoliving_app no tiene BYPASSRLS, asi que las politicas se aplican de
-- verdad. Sin el SET LOCAL ROLE, el rol de conexion de Supabase las ignoraria y RLS
-- seria decorativo.
--
-- usuario, token_email e intento_acceso quedan fuera de RLS a proposito: se consultan
-- durante el login, antes de que exista una identidad que filtrar. Su proteccion es
-- que solo el codigo de autenticacion las toca, siempre con consultas parametrizadas.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mycoliving_app') THEN
        CREATE ROLE mycoliving_app NOLOGIN;
    END IF;
    -- Sin esta pertenencia, el rol con el que se conecta la aplicacion no puede
    -- hacer SET LOCAL ROLE y cada transaccion fallaria al arrancar.
    EXECUTE format('GRANT mycoliving_app TO %I', current_user);
END
$$;

GRANT USAGE ON SCHEMA public TO mycoliving_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mycoliving_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mycoliving_app;

-- Devuelve el dueno de la transaccion actual, o NULL si no se ha fijado.
-- El segundo argumento (missing_ok) evita que reviente cuando no hay sesion.
CREATE OR REPLACE FUNCTION app_usuario_id() RETURNS BIGINT AS $$
    SELECT nullif(current_setting('app.usuario_id', true), '')::BIGINT;
$$ LANGUAGE sql STABLE SET search_path = public, pg_temp;

ALTER TABLE activo                ENABLE ROW LEVEL SECURITY;
ALTER TABLE contrato_maestro      ENABLE ROW LEVEL SECURITY;
ALTER TABLE politica_distribucion ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracion_dominio ENABLE ROW LEVEL SECURITY;
ALTER TABLE capex                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordatorios         ENABLE ROW LEVEL SECURITY;
ALTER TABLE reporte_mensual       ENABLE ROW LEVEL SECURITY;
ALTER TABLE reporte_unidad        ENABLE ROW LEVEL SECURITY;
ALTER TABLE reserva_movimiento    ENABLE ROW LEVEL SECURITY;
ALTER TABLE asesoria_generada     ENABLE ROW LEVEL SECURITY;
ALTER TABLE uso_asesoria          ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_activo ON activo;
CREATE POLICY p_activo ON activo
    USING (usuario_id = app_usuario_id())
    WITH CHECK (usuario_id = app_usuario_id());

DROP POLICY IF EXISTS p_uso_asesoria ON uso_asesoria;
CREATE POLICY p_uso_asesoria ON uso_asesoria
    USING (usuario_id = app_usuario_id())
    WITH CHECK (usuario_id = app_usuario_id());

-- Las tablas hijas se validan contra el activo del usuario. La subconsulta a `activo`
-- pasa por su propia politica, asi que basta con comprobar la pertenencia.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'contrato_maestro', 'politica_distribucion', 'configuracion_dominio',
        'capex', 'recordatorios', 'reporte_mensual', 'reserva_movimiento',
        'asesoria_generada'
    ] LOOP
        EXECUTE format('DROP POLICY IF EXISTS p_%1$s ON %1$s', t);
        EXECUTE format(
            'CREATE POLICY p_%1$s ON %1$s
               USING (activo_id IN (SELECT id FROM activo WHERE usuario_id = app_usuario_id()))
               WITH CHECK (activo_id IN (SELECT id FROM activo WHERE usuario_id = app_usuario_id()))',
            t
        );
    END LOOP;
END
$$;

-- Las tablas de cuentas tambien llevan RLS, pero *sin ninguna politica*: eso niega
-- todas las filas a cualquier rol sin BYPASSRLS, incluido mycoliving_app. Solo el rol de
-- conexion (modo privilegiado de db_cursor, que usa unicamente web/auth.py y db/usuarios.py)
-- puede leerlas. Ver la seccion siguiente para por que importa.
ALTER TABLE usuario        ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_email    ENABLE ROW LEVEL SECURITY;
ALTER TABLE intento_acceso ENABLE ROW LEVEL SECURITY;

-- reporte_unidad no tiene activo_id: llega a su dueno por el reporte padre.
DROP POLICY IF EXISTS p_reporte_unidad ON reporte_unidad;
CREATE POLICY p_reporte_unidad ON reporte_unidad
    USING (reporte_mensual_id IN (
        SELECT rm.id FROM reporte_mensual rm
        JOIN activo a ON a.id = rm.activo_id
        WHERE a.usuario_id = app_usuario_id()
    ))
    WITH CHECK (reporte_mensual_id IN (
        SELECT rm.id FROM reporte_mensual rm
        JOIN activo a ON a.id = rm.activo_id
        WHERE a.usuario_id = app_usuario_id()
    ));


-- ---------------------------------------------------------------------------
-- Cierre de la Data API de Supabase
-- ---------------------------------------------------------------------------

-- Supabase publica el esquema public por HTTP (PostgREST, en /rest/v1/) para los roles
-- anon y authenticated, y la clave de anon es publica por diseno. Ademas, en ese esquema
-- concede por defecto todos los permisos sobre las tablas nuevas a esos dos roles. Sin
-- este bloque, cualquiera con la URL del proyecto podria leer la tabla usuario.
--
-- La aplicacion no usa la Data API: habla con Postgres directamente. Asi que se les quita
-- todo. En Postgres local y en CI esos roles no existen y el bloque no hace nada.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
    END IF;
END
$$;

-- Postgres concede EXECUTE a PUBLIC en toda funcion nueva, y PostgREST expone las del
-- esquema public como /rest/v1/rpc/<nombre>. Se retira, y se devuelve solo donde hace
-- falta: las politicas de aislamiento evaluan app_usuario_id() con el rol de la app.
REVOKE EXECUTE ON FUNCTION app_usuario_id(), limpiar_intentos_viejos(), fn_valida_ocupacion() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_usuario_id() TO mycoliving_app;
