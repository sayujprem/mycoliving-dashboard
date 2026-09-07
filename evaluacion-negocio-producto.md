# Evaluación de negocio y producto — Family Office de un solo activo (MyColiving)

Fecha: 2026-08-29
Insumos: `specs-family-office-coliving (1).md`, `mockup-family-office-coliving.html`, `sobre-mi.md`.

## Hallazgo central

El spec modela a un propietario. La operación real es rent-to-rent: contrato maestro de arriendo con la dueña (con cláusula de subarriendo) y contrato de administración con una inmobiliaria que opera el coliving y cobra 10% sobre los recaudos de subarriendo. El objeto que el sistema debe modelar es el spread entre un pago fijo (canon a la dueña) y un ingreso variable (recaudo de subarriendos), no el inmueble.

## 1. Huecos de negocio

- El costo fijo dominante (canon maestro) no está en el modelo. `reporte_mensual` guarda `gastos_totales` agregado y el semáforo usa margen porcentual. Falta lo único que importa cada mes: cuántas unidades ocupadas se necesitan para no poner plata.
- Punto de equilibrio ausente. El semáforo mide ocupación contra umbral fijo, no contra el break-even económico.
- La renovación del contrato maestro es el riesgo número uno y está como un recordatorio cualquiera, junto a "pintura de fachada".
- El informe de la inmobiliaria: confirmar que trae ocupación por unidad, ingresos de subarriendo y gastos, y no solo el estado del contrato de administración.
- No hay concepto de mes con spread negativo. La política reparte 100% asumiendo que siempre sobra.
- Capex de montaje y su recuperación no existen en el modelo.
- "Pasivo" no se sostiene con contratos de 6 meses sobre 5 unidades: la reposición es constante.
- El bucle de adopción repite el problema: el sistema exige carga manual mensual, sin disparador externo.
- Asesoría fiscal sobre el activo aislado es frágil: la deducibilidad del canon maestro y la interacción con la renta global son el punto.

## 2. Costo de cada hueco

Baratos ahora (edición de spec/flujo): reencuadre del proyecto, descomposición de `gastos_totales`, redefinición del semáforo, reemplazo de `horizonte_patrimonial` por `contrato_maestro`, regla del mes negativo.

Caros después (rehacer lo construido): informe de la inmobiliaria distinto a lo asumido, módulo fiscal mal encuadrado, prompts del Paso 5 con marco de propietario, scaffolding multi-activo que no se usa.

## 3. Lo que sobra

`horizonte_patrimonial` con vender/legado; separación motor/dominio y `activo_id` universal; `configuracion_dominio` como tabla clave-valor; dos semáforos con diales; el criterio de "no encontrar el 5 ni el 10% en el repo"; `porcentaje_reinversion` como bolsillo fijo mensual.

## 4. Contradicciones

- Spec ("inversionista pasivo", "family office", "vender/legado") contra negocio (subarriendo sin propiedad).
- Spec contra spec: "un solo activo en esta versión" y a la vez exigencia de multi-activo sin tocar código.
- Spec contra mockup: constantes `UNIDADES_TOTALES = 5` y umbrales en el JavaScript, prohibido por el criterio 8.
- `tarifa_marginal_actual` (0-19%) sin origen ni cálculo especificado en ningún paso
  (resuelto el 2026-08-29: ver cierre al final).
- Mockup: `libreReal = margen` compara dos cosas distintas contra la meta de libre.

## 5. Decisiones tomadas (2026-08-29)

1. Marco: se mantiene el nombre "family office" (opción 1b). Nota abierta: `horizonte_patrimonial` con vender/legado sigue sin aplicar y debe repurposarse a `contrato_maestro`.
2. Dato mensual: informe único de la inmobiliaria (2a), que trae ocupación por unidad, ingresos de subarriendo y gastos, porque su contrato de administración es con Nelson.
3. Comisión: 10% sobre los recaudos de subarriendo.
4. Semáforo financiero: ocupación real contra ocupación de equilibrio (4a).
5. Mes con spread negativo: la reserva lo cubre; el sistema registra consumo y meses de reserva restantes (5a).
6. Fiscal: se amplía a cómo se declara el subarriendo — deducibilidad del canon maestro, gastos asociados, cédula general, sin calcular la renta total (6b).
7. Capex: solo zonas comunes (sala-comedor, cocina, patio de ropas), no habitaciones. Modelado aún por decidir.
8. Reutilización: se mantiene la separación motor/dominio y el `activo_id` universal, con el sobrecosto asumido (8c).
9. Despliegue: local, con recordatorio en calendario externo (9a).

## Pendientes reales

- Composición del resultado del mes: recaudo de subarriendo − comisión (10% del recaudo) − gastos de operación − canon maestro. El canon maestro no viene en el informe; es valor fijo del contrato con la dueña, se registra una vez.
- Fórmula de ocupación de equilibrio ≈ (canon maestro + gastos fijos) / (arriendo promedio por unidad × 0,9). Requiere dos datos nuevos en el modelo: arriendo promedio por unidad y separación de gastos en fijos y variables.
- Confirmar con un informe real que trae ocupación unidad por unidad y el desglose de gastos que el semáforo de equilibrio necesita.
- Capex de zonas comunes: registrarlo como monto único con recuperación contra la vigencia del contrato, o dejarlo fuera de la V1.
- Tratamiento fiscal de los costos del periodo de remodelación (canon maestro sin ingreso, adecuación de zonas comunes): la compensación de pérdidas dentro de la cédula general es limitada; confirmar con el contador.

## Cierre 2026-08-29 — `tarifa_marginal_actual`

El tope 0-19% del spec es un cap arbitrario: el 19% es solo el primer tramo gravado de la tabla del art. 241 del Estatuto Tributario (0%, 19%, 28%, 33%, 35%, 37%, 39%), no un techo real. La tarifa marginal la fija la renta gravable total del año en la cédula general (el subarriendo entra como renta no laboral), no el coliving aislado. Hoy es 0% porque el inmueble está en remodelación y no hay recaudo.

Ajuste al spec: el campo admite el rango completo 0-39% y lo ingresa Nelson según lo que le indique su contador para el año, o el sistema no calcula impuesto y solo recuerda que el resultado neto del coliving se suma a la renta.
