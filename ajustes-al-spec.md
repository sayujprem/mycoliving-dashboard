# Cierre de la evaluación previa — MyColiving (Family Office de un solo activo)

## Context

Nelson pidió evaluar la idea del producto **antes** de construirlo, como negocio y como
producto, no como revisión técnica. No quiere que se reescriba el spec todavía ni que se
proponga arquitectura. La evaluación completa ya está en
`outputs/mycoliving-dashboard/evaluacion-negocio-producto.md`.

Hallazgo central: el spec modela a un propietario, pero la operación es rent-to-rent
(contrato maestro de arriendo con la dueña + contrato de administración con una inmobiliaria
que cobra 10% sobre recaudos de subarriendo). El sistema debe modelar el spread entre un
pago fijo (canon a la dueña) y un ingreso variable (recaudo de subarriendos).

Nelson ya tomó las nueve decisiones pendientes. Este documento consolida qué cambia en el
spec por esas decisiones y qué queda abierto. No es un plan de implementación de código: es
la lista de ajustes al spec que Nelson hará (o encargará) antes de construir.

## Decisiones tomadas

1. Se mantiene el nombre "family office" (1b).
2. Dato mensual: informe único de la inmobiliaria (2a), con ocupación por unidad, ingresos
   de subarriendo y gastos.
3. Comisión: 10% sobre recaudos de subarriendo.
4. Semáforo financiero: ocupación real vs. ocupación de equilibrio (4a).
5. Mes con spread negativo: la reserva lo cubre; se registra consumo y meses restantes (5a).
6. Fiscal: se amplía a cómo se declara el subarriendo — deducibilidad del canon maestro,
   gastos asociados, cédula general, sin calcular la renta total (6b).
7. Capex: solo zonas comunes (sala-comedor, cocina, patio de ropas), no habitaciones.
8. Reutilización: se mantiene motor/dominio y `activo_id` universal, sobrecosto asumido (8c).
9. Despliegue: local, con recordatorio en calendario externo (9a).

## Ajustes al spec que fuerzan estas decisiones

- **Reemplazar `horizonte_patrimonial` (vender / legado) por `contrato_maestro`**: fecha de
  vencimiento, canon vigente, fórmula de reajuste, ventana de preaviso. Aunque se conserve
  el nombre "family office" (1b), vender y legado no aplican a un activo ajeno.
- **Descomponer `gastos_totales`** en `reporte_mensual`: recaudo de subarriendo, comisión
  (10% del recaudo), gastos de operación. El resultado del mes = recaudo − comisión −
  gastos de operación − canon maestro.
- **Canon maestro como valor fijo de configuración**, no como campo del informe mensual: vive
  en `contrato_maestro`, se registra una vez.
- **Semáforo financiero (4a)**: definir la fórmula de ocupación de equilibrio
  ≈ (canon maestro + gastos fijos) / (arriendo promedio por unidad × 0,9). Requiere dos
  datos nuevos en el modelo: arriendo promedio por unidad y separación de gastos en fijos y
  variables.
- **Reserva de contingencia (5a)**: agregar el registro de consumo mensual y el cálculo de
  meses de reserva restantes contra el déficit esperado a la ocupación actual.
- **Módulo fiscal (6b)**: reencuadrar a reglas de subarriendo como renta no laboral dentro
  de la cédula general. El `tarifa_marginal_actual` con tope 0-19% del spec es un cap
  arbitrario: el 19% es solo el primer tramo gravado del art. 241 ET, no un techo real.
  Resolución: el campo admite el rango completo 0-39% y lo ingresa Nelson según lo que le
  indique su contador para el año, o el sistema no calcula impuesto y solo recuerda que el
  resultado neto del coliving se suma a la renta. La tarifa marginal la fija la renta
  gravable total del año, no el coliving aislado; hoy es 0% porque el inmueble está en
  remodelación y no hay recaudo.
- **Semáforo**: dejar de mostrar "margen %" como métrica principal; usar resultado del mes en
  pesos y ocupación vs. equilibrio.
- **Mockup**: las constantes `UNIDADES_TOTALES = 5` y los umbrales en el JavaScript
  contradicen el criterio 8 del propio spec; anotarlo como deuda del prototipo, no del spec.

## Pendientes reales — resueltos el 2026-08-29

- **Capex de zonas comunes**: se modela como monto único, con seguimiento de recuperación
  (payback) contra la vigencia del contrato maestro, tentativamente 5 años. La vigencia es
  un dato de `contrato_maestro`.
- **Tratamiento fiscal del periodo de remodelación**: fuera de alcance. El módulo fiscal
  solo actúa sobre meses con operación e ingreso; no modela los costos previos a la puesta
  en marcha.
- **Formato del informe de la inmobiliaria**: confirmado por Nelson (de memoria, sin la
  imagen a mano). El informe incluye ocupación por unidad, desglose de ingresos por
  inquilino, y gastos separados en fijos y variables, con el 10% de la inmobiliaria como
  línea propia. Queda como supuesto a validar contra un informe real antes de construir el
  Paso 1.

## Ajuste de alcance — 2026-09-01

Nelson pidió entregar la plataforma funcional **sin exigir el contrato maestro**, solo con
el registro mensual del informe y un **horizonte temporal ajustable**.

- `contrato_maestro` pasa a ser opcional en toda la app. Si no está definido, la obligación
  fija del periodo es 0 y se asume que el canon (si aplica) ya viene incluido en
  `gastos_fijos` del informe mensual.
- Nueva configuración en `configuracion_dominio`: `horizonte_meses` (ventana temporal,
  default 60) y `horizonte_destino` (texto libre). Reemplaza a `contrato.vigencia_meses`
  como referencia por defecto para el ritmo de recuperación del capex y para la ventana que
  enmarca la asesoría, cuando no hay contrato maestro.
- El panel muestra una tarjeta "Horizonte" (ventana + destino) en vez de depender de
  "Contrato maestro"; si el contrato existe, sus datos aparecen como bloque adicional.
- `/config` marca el contrato maestro como "(opcional)".

## Verificación

Esta fase no produce código. El cierre se verifica así:

1. Nelson revisa `outputs/mycoliving-dashboard/evaluacion-negocio-producto.md` y confirma que
   las nueve decisiones quedaron bien registradas.
2. Nelson resuelve los tres pendientes reales de arriba.
3. Con eso, el siguiente paso (fuera de este alcance) es reescribir el spec con la skill
   `crear-specs` o `design-spec`, usando este documento como insumo.
