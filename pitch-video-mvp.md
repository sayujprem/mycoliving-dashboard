# Pitch — Video MVP (2 minutos) — MyColiving Dashboard

Guion para grabar. Tiempos calculados a ~150 palabras por minuto.
Los `[corchetes]` son datos tuyos que hay que reemplazar con las cifras reales antes de grabar.

---

## Sección 1 — El problema (~25 s, 68 palabras)

> "Hoy, quien subarrienda un coliving recibe cada mes el informe de la inmobiliaria, lo lee una vez y lo archiva. Nadie le dice si el mes fue bueno. El negocio es un spread: canon fijo a la propietaria contra un recaudo variable que depende de cuántas habitaciones estén ocupadas. Cuando ese spread se pone negativo, uno se entera tres meses después, cuando ya se comió la reserva."

---

## Sección 2 — Quién tiene el problema (~14 s, 36 palabras)

> "Es mi caso: cinco apartaestudios en Armenia, contrato maestro con la dueña, una inmobiliaria que opera y cobra el 10% del recaudo. Con un solo activo y sin equipo, un mes mal leído se paga del bolsillo."

---

## Sección 3 — Cómo lo resuelve + demo (~58 s, 145 palabras)

Empieza la pantalla compartida.

> "Construí un tablero que convierte ese informe mensual en un diagnóstico: si el mes fue bueno o malo, por qué, y qué hacer con lo que sobró.
>
> **[pantalla: /registro]** Entro a registrar el mes y copio lo que ya viene en el informe: ocupación por unidad, ingresos, gastos fijos, gastos variables y la comisión. Guardo. Menos de dos minutos.
>
> **[pantalla: panel]** Esto es lo que devuelve. Ocupación de equilibrio: necesito **[X]** unidades arrendadas para no poner plata este mes, y tuve **[Y]**. Ese número antes no existía en ninguna parte.
>
> El color sale de una regla fija que yo definí, y el tablero explica en una línea por qué está en ese color. Al lado veo cuánto quedó libre de verdad contra mi política de distribución, cuántos meses de reserva quedan y qué vencimientos se acercan.
>
> **[pantalla: asesoría]** Y esta es la única parte con IA: me nombra la causa concreta de la brecha del mes, con la cifra, más una nota de cómo se declara este ingreso, siempre con la advertencia de que estima solo este activo."

---

## Sección 4 — Call to action (~19 s, 48 palabras)

> "Esta es la versión uno y corre local, así que no hay link para probarlo: les dejo la pregunta. ¿El panel se entiende sin que yo lo explique? Si ves la captura y no sabes qué deberías hacer al día siguiente, eso es lo que necesito que me digas en el comentario."

---

## Antes de grabar

- [ ] **Cargar datos de prueba creíbles.** La base tiene un solo mes con cifras redondas de prueba (ingreso 1.000.000, gastos 300.000/450.000). Registra **3 o 4 meses** con cifras reales o realistas, incluyendo **un mes en amarillo o rojo**: sin un mes malo, el semáforo no demuestra nada.
- [ ] Definir el canon maestro (o dejarlo dentro de gastos fijos) para que la ocupación de equilibrio dé un número honesto. Reemplaza `[X]` e `[Y]` con lo que salga en pantalla.
- [ ] Generar la asesoría del mes que vas a mostrar **antes** de grabar (consume API y tarda). Verifica que salga con la advertencia de alcance.
- [ ] Levantar el servidor: `uvicorn main:app --port 8000`. Se cae al cerrar la sesión, relánzalo el día de la grabación.
- [ ] Dejar tres pestañas abiertas y en orden: `/registro`, `/` (panel), `/asesoria/{año}/{mes}`.
- [ ] Cronometrar una pasada. Si te pasas de 2:00, corta la Sección 3 por la parte de recordatorios.

---

## Qué poner en la plataforma de La 10

| Campo | Qué poner |
|---|---|
| Nombre | MyColiving Dashboard |
| Descripción en una frase | Tablero mensual que le dice a un operador de rent-to-rent si el mes dio o no dio, y qué hacer con el resultado. |
| Etapa | MVP |
| Industria | Inmobiliario / Fintech |
| ¿Qué buscas? | Feedback |
| Link de acceso | No aplica (corre local). Dilo explícito en la descripción. |

**Descripción adicional sugerida:**

> Opero un coliving de 5 unidades en Armenia bajo modelo rent-to-rent. El sistema no administra el inmueble: mide el spread entre el canon fijo que pago y el recaudo variable que entra, y traduce el informe mensual de la inmobiliaria en un semáforo con explicación. Busco feedback sobre una cosa: si el panel comunica la decisión del mes a alguien que no vive el problema.

**Mensaje para el grupo de la cohorte:**

> Publiqué mi MVP: un tablero que le dice a un operador de subarriendo si el mes dio o no dio. Me interesa feedback en un punto específico: mirando el panel, sin que yo explique nada, ¿sabrías qué hacer el mes siguiente?
