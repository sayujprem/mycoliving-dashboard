# Política de privacidad

Última actualización: 10 de septiembre de 2026

## Quién es el responsable

MyColiving Dashboard es un proyecto personal y gratuito de Nelson García, persona natural
domiciliada en Colombia. Él es el responsable del tratamiento de los datos que se registran
en la plataforma, en los términos de la Ley 1581 de 2012.

Contacto para cualquier asunto de datos personales: privacidad.mycoliving@gmail.com.

## Qué datos guardamos

**De tu cuenta:** tu correo y tu contraseña. La contraseña no se guarda: se guarda una huella
irreversible de ella (un hash con scrypt), así que nadie, ni siquiera el responsable, puede
leerla.

**De tu activo:** lo que tú registras. Nombre, tipo, número de unidades, comisión del
administrador, moneda, ubicación y notas del activo; el contrato maestro; la política de
distribución; cada mes registrado, con sus gastos, las unidades arrendadas y el ingreso de
cada una, y las novedades que escribas; las inversiones de montaje; los recordatorios, y los
informes de asesoría generados.

La plataforma no te pide datos de tus inquilinos y no los necesita. Si escribes alguno en un
campo de texto libre (por ejemplo, en las novedades del mes), queda guardado como lo
escribiste.

**Registros de seguridad:** cuando alguien intenta entrar, crear una cuenta o recuperar una
contraseña, guardamos el correo usado, la dirección IP y la hora. Sirven para frenar ataques
de fuerza bruta y se borran solos en un plazo de 7 días.

## Para qué los usamos

Para una sola cosa: que la plataforma funcione. Calcular tu resultado mensual, tus
semáforos, tu fondo de reserva y tus recordatorios, y mostrártelos a ti.

No vendemos datos. No hacemos publicidad. No usamos analítica ni rastreo de ningún tipo.

## Quién más los procesa

La plataforma se apoya en servicios de terceros, que procesan datos por cuenta del
responsable. Todos operan servidores en Estados Unidos:

- **Vercel** aloja la aplicación.
- **Supabase** aloja la base de datos.
- **Google** envía, por Gmail y desde privacidad.mycoliving@gmail.com, los correos de
  verificación y de recuperación de contraseña, así que recibe tu correo y el texto del
  mensaje. También sirve las tipografías de la interfaz: tu navegador se las pide
  directamente, así que Google ve tu dirección IP.
- **Anthropic** redacta el informe de asesoría, pero solo en las cuentas que tienen esa
  función habilitada y solo cuando la pides. Recibe cifras agregadas del mes (resultado,
  brecha frente a tu política, saldo del fondo de reserva, porcentaje de inversión
  recuperada, meses de contrato restantes) y las **notas de contexto** que escribiste en la
  configuración del activo. No recibe tu correo, ni el nombre ni la ubicación del activo, ni
  el ingreso por unidad.
- **Google Drive** guarda las copias de respaldo, cifradas con AES-256 antes de salir de la
  plataforma. Sin la clave de cifrado, que no está en Drive, el archivo es ilegible.

Al crear la cuenta autorizas que tus datos se almacenen y procesen en esos servidores.

## Cuánto tiempo los guardamos

Mientras tengas la cuenta. Si la eliminas, se borran de inmediato de la base de datos, con
todo lo que registraste.

Pueden seguir existiendo en las copias de respaldo cifradas, que se hacen una vez al mes para
recuperar la plataforma ante una falla. Se conservan 12 y la más antigua se elimina sola.
Esas copias no se consultan salvo para restaurar el servicio.

## Tus derechos

Como titular de los datos puedes conocerlos, actualizarlos, rectificarlos, pedir que se
supriman y revocar la autorización que diste.

- **Actualizar o corregir:** directamente en la plataforma, en cualquier momento.
- **Suprimir todo:** en *Tu cuenta → Eliminar la cuenta*. Es inmediato.
- **Cualquier otra solicitud**, o una queja: escribe a privacidad.mycoliving@gmail.com.
  Se responde en un máximo de 10 días hábiles para consultas y 15 para reclamos, como fija
  la ley.

Si no quedas conforme con la respuesta, puedes acudir a la Superintendencia de Industria y
Comercio.

## Seguridad

Cada cuenta está aislada de las demás en dos capas: la aplicación solo consulta los datos de
quien tiene la sesión abierta, y la propia base de datos rechaza cualquier consulta sobre
datos de otra cuenta, aunque la aplicación la pidiera por error. Las conexiones van cifradas
(HTTPS), la sesión viaja en una cookie firmada que JavaScript no puede leer, y los intentos
repetidos de acceso se bloquean.

Ningún sistema es invulnerable. Si detectamos un incidente que afecte tus datos, te lo
comunicaremos por correo.

## Cookies

Una sola: `mcl_sesion`, que mantiene tu sesión abierta hasta por 14 días. Es técnica e
imprescindible para que puedas entrar. No hay cookies de publicidad, de analítica ni de
terceros.

## Menores de edad

La plataforma no está dirigida a menores de 18 años.

## Cambios

Si esta política cambia en algo que te afecte, te avisaremos por correo antes de que el
cambio empiece a regir. Cada versión queda en el historial público del repositorio.
