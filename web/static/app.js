// Único script de la aplicación. La política de seguridad (web/seguridad.py) prohíbe
// JavaScript en línea, así que los comportamientos que antes vivían en atributos
// onclick se declaran en el HTML con data-* y se conectan desde acá.

document.addEventListener("submit", function (evento) {
  var formulario = evento.target;

  // Formularios destructivos: <form data-confirmar="mensaje"> pide confirmación
  // antes de enviarse.
  var mensaje = formulario.dataset && formulario.dataset.confirmar;
  if (mensaje && !window.confirm(mensaje)) {
    evento.preventDefault();
    return;
  }

  // Un solo envío por clic. Sin esto, un doble clic en "Regenerar" dispara dos
  // llamadas al modelo y se pagan las dos. Se deshabilita después de que el
  // navegador ya tomó la decisión de enviar, así que no bloquea el envío.
  var botones = formulario.querySelectorAll('button[type="submit"]');
  window.setTimeout(function () {
    botones.forEach(function (b) { b.disabled = true; });
  }, 0);
});

// Al volver con el botón "atrás", el navegador restaura la página desde memoria con
// los botones todavía deshabilitados. Se reactivan.
window.addEventListener("pageshow", function (evento) {
  if (evento.persisted) {
    document.querySelectorAll('button[type="submit"]:disabled').forEach(function (b) {
      b.disabled = false;
    });
  }
});
