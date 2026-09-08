# Política de privacidad — MyColiving Dashboard

Última actualización: 8 de septiembre de 2026

## Qué es esta aplicación

MyColiving Dashboard es una herramienta personal de uso local. Se instala y se ejecuta en el
computador de quien la usa. No es un servicio en línea, no tiene servidores, no tiene cuentas
de usuario y no hay ningún operador que reciba datos de terceros.

## Qué datos maneja y dónde viven

Todos los datos que registra el usuario —cifras de ocupación, ingresos, gastos y
configuración del inmueble— se guardan en un archivo SQLite en su propio computador. No se
envían a ninguna parte salvo en los dos casos descritos abajo, y ambos van a servicios que el
propio usuario configura con sus propias credenciales.

El desarrollador de esta aplicación no recibe, almacena ni tiene acceso a ningún dato de
quien la usa.

## Uso del acceso a Google Drive

La aplicación puede subir una copia de seguridad de su base de datos a la cuenta de Google
Drive del propio usuario, usando [rclone](https://rclone.org). Ese acceso:

- Lo autoriza el usuario explícitamente, desde su computador.
- Se usa únicamente para escribir, listar y rotar los archivos de respaldo de esta
  aplicación, dentro de una carpeta que el usuario elige.
- No lee, analiza ni transmite ningún otro contenido del Drive.
- Guarda el token de acceso solo en el computador del usuario, en la configuración local de
  rclone. Nunca se transmite a terceros.

El usuario puede revocar este acceso cuando quiera desde
[la página de permisos de su cuenta de Google](https://myaccount.google.com/permissions), o
borrando el remoto con `rclone config delete`.

## Uso de la API de Anthropic

Si el usuario configura una clave propia de la API de Anthropic, la aplicación puede enviar
el resumen numérico de un mes (resultado, brecha, estado de la reserva, recuperación de la
inversión) para redactar el informe de asesoría de ese mes. Esa función es opcional: el resto
de la aplicación funciona sin ella. No se envían datos identificatorios de inquilinos ni de
personas.

## Menores de edad

La aplicación no está dirigida a menores de edad ni recoge datos de ellos.

## Cambios

Cualquier cambio a esta política quedará registrado en el historial público de este
repositorio.

## Contacto

A través de las [incidencias del repositorio](https://github.com/sayujprem/mycoliving-dashboard/issues).
