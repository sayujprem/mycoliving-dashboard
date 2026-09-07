# Spec: MyColiving Dashboard (family office de un solo activo)
Fecha: 2026-08-29

## Overview

Aplicación web personal, de un solo usuario, que sirve de capa de criterio mensual sobre una operación de subarriendo. El usuario tiene un contrato maestro de arriendo sobre una casa, con permiso de subarriendo de la propietaria, y subarrienda 5 apartaestudios como coliving; una inmobiliaria opera el día a día y cobra 10% de lo recaudado. Cada mes llega un informe de la inmobiliaria y el usuario debe decidir qué hacer con el resultado. El sistema convierte ese informe en un diagnóstico claro: si el mes fue bueno o malo y por qué, si el resultado cumple la meta de distribución, qué vencimientos se acercan, y una recomendación financiera y fiscal concreta. Reemplaza el juicio manual mes a mes por un criterio consistente y repetible.

## Usuarios objetivo

Un inversionista en modelo rent-to-rent con un solo activo, sin equipo. Hoy recibe el informe de la inmobiliaria, lo lee una vez y lo archiva. No tiene un criterio sistemático para juzgar el mes, ni un mecanismo que le recuerde los vencimientos de seguros, mantenimiento o la renovación del contrato maestro, ni asesoría fiscal aplicada a ese ingreso. Todo depende de que se acuerde de revisar y de interpretar cada cosa por su cuenta. Trabaja con hoja de cálculo y correo, y no viene de una carrera técnica.

## Alcance

### La v1 SÍ hace

1. **Registro mensual del informe.** El usuario copia del informe de la inmobiliaria los campos del mes: ocupación por unidad, ingreso por inquilino, gastos fijos, gastos variables y la comisión del 10%. Meta: registrar el mes completo en menos de dos minutos.

2. **Diagnóstico del mes.** Con reglas determinísticas y umbrales que el usuario define, el sistema calcula y muestra:
   - Resultado del mes en pesos: recaudo de subarriendo, menos comisión, menos gastos de operación, menos el canon del contrato maestro.
   - Ocupación real contra la ocupación de equilibrio, es decir las unidades que hay que tener arrendadas para no perder plata ese mes.
   - Un semáforo (verde, amarillo, rojo) por resultado y por ocupación, cada uno con una explicación en lenguaje simple de por qué está en ese color.
   - Regla de vacancia: si la ocupación se mantiene baja durante el número de meses que el usuario definió, el semáforo de ocupación marca rojo.
   - Brecha contra la meta: cuánto quedó realmente libre frente a la política de distribución, si la reserva de contingencia se cubrió o se consumió, y cuántos meses de reserva quedan.
   - Recuperación del capex: cuánto se ha recuperado de la inversión en zonas comunes frente a la vigencia del contrato.
   - Un panorama consolidado consultable cualquier día del mes, con el histórico de meses y sus semáforos.

3. **Recordatorios de vencimientos.** Alertas por fecha para la renovación del contrato maestro, los seguros y el mantenimiento, con aviso antes del vencimiento. El usuario define cada recordatorio con su fecha fija o su frecuencia.

4. **Informe mensual de asesoría.** El sistema genera de forma automática un texto que nombra la causa concreta de la brecha del mes, una recomendación de reinversión, y una nota de optimización tributaria bajo el marco colombiano (Estatuto Tributario, leyes 2277 de 2022 y 2010 de 2019). Todo cálculo tributario se muestra con la advertencia de que es una estimación basada solo en el ingreso de este activo, no en la situación fiscal total del usuario, y que no cubre el periodo de remodelación.

### La v1 NO hace

- No consolida las otras fuentes de ingreso del usuario, ni calcula su declaración de renta completa, ni su posición fiscal total.
- No modela el periodo de remodelación previo a la operación ni sus costos para efectos fiscales.
- No reemplaza a la inmobiliaria: nada de portal de inquilinos, cobros, firma de contratos de arrendamiento ni gestión operativa.
- No interpreta informes en texto libre. Asume que el informe llega con campos estables; si un mes cambia el formato, el usuario ajusta los valores a mano.
- No decide el color del semáforo con un modelo de lenguaje. Ese juicio es determinístico.
- No tiene login, roles ni varios usuarios.
- No gestiona más de un activo a la vez.
- No tiene app móvil ni acceso remoto. Corre en la máquina del usuario, que se apoya en un recordatorio de calendario para cargar el mes.

## Comportamiento esperado

**Configuración inicial, una sola vez.** El usuario registra el activo: nombre, número de unidades, comisión del administrador, ubicación y notas de contexto como zonas comunes y estrato. Registra el contrato maestro: canon mensual que paga a la propietaria, fecha de vencimiento, vigencia estimada (tentativa de 5 años), regla de reajuste y ventana de preaviso. Define la política de distribución con tres porcentajes que deben sumar 100: libre disponible, reinversión y reserva de contingencia. Define los umbrales del diagnóstico: ocupación mínima para verde, gasto máximo para verde, y número de meses seguidos de baja ocupación para marcar rojo. Registra la inversión en zonas comunes con su monto y su fecha. Crea los recordatorios de seguro, mantenimiento y revisión del contrato maestro.

**Cada mes, cuando llega el informe.** El usuario abre la aplicación, entra a "registrar mes" y copia del informe el mes y año, la ocupación por unidad, el ingreso por inquilino, los gastos fijos, los gastos variables y la comisión del 10%. Guarda.

**El sistema responde de inmediato.** Muestra el resultado del mes en pesos y el semáforo por resultado y por ocupación, cada uno con su explicación. Muestra la ocupación real contra la de equilibrio. Muestra la brecha contra la meta de distribución, el estado de la reserva y los meses de reserva que quedan. Muestra cuánto se ha recuperado de la inversión en zonas comunes. Lista los recordatorios vencidos y los próximos. Genera el informe mensual de asesoría con su advertencia de alcance.

**En cualquier momento.** El usuario entra al panorama consolidado y ve el histórico de meses con sus semáforos, la evolución de la brecha y el avance de recuperación del capex, sin esperar al cierre de mes.

## Errores y seguridad

- **Primer mes, sin histórico.** El diagnóstico funciona con el mes cargado. La regla de vacancia y las tendencias quedan en espera hasta tener suficientes meses, y el sistema lo indica en vez de mostrar un resultado en falso.
- **Informe con formato distinto al esperado.** El sistema no adivina. El usuario ajusta los valores a mano y el sistema valida que estén dentro de rangos razonables antes de guardar.
- **Ocupación mayor que el número de unidades del activo.** Se rechaza el registro con un mensaje claro.
- **Ingresos o gastos vacíos.** Se rechaza el registro.
- **Los tres porcentajes de la política no suman 100.** Se rechaza hasta corregir.
- **Mes con resultado negativo.** El semáforo marca rojo, el sistema registra cuánto se tomó de la reserva y cuántos meses de reserva quedan. Si la reserva se agota, lo alerta de forma explícita.
- **Servicio de asesoría no disponible.** Si el generador del informe falla o no hay crédito, el diagnóstico determinístico se muestra igual y el informe de asesoría queda pendiente de reintento.
- **Cálculo tributario.** Nunca se muestra sin la advertencia de que es una estimación sobre el ingreso de este activo, no sobre la situación fiscal total, y que excluye el periodo de remodelación.
- **Datos.** Viven en la máquina del usuario. Un solo usuario, sin exposición a terceros. La única salida a un servicio externo es el texto que se envía para generar el informe de asesoría, con esquema validado antes de enviarlo.

## Éxito

- El usuario registra un mes completo en menos de dos minutos.
- El semáforo explica en lenguaje simple por qué está en el color que está, sin jerga financiera.
- La asesoría del mes nombra una cifra concreta y una causa concreta, nunca un consejo genérico.
- Los recordatorios avisan antes del vencimiento, no después.
- Ningún cálculo tributario aparece sin su advertencia de alcance.
- El usuario consulta el estado del activo cualquier día del mes, no solo al cierre.
- Cuando un mes da pérdida, el usuario ve de inmediato cuánto costó y cuánta reserva le queda.

## V2 (opcional)

- Consolidación de las otras fuentes de ingreso y cálculo de la posición fiscal total.
- Interpretación de informes en texto libre con un modelo de lenguaje.
- Juicio del semáforo asistido por un modelo, además de la regla determinística.
- Varios activos y varios usuarios.
- Acceso remoto con aviso automático cuando toca cargar el mes.
- Tratamiento fiscal del periodo de remodelación y sus costos.
- Reajuste automático del canon maestro por IPC.
