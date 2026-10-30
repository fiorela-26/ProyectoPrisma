(function () {
  var caja = document.getElementById("mediacion-tema");
  if (!caja) return;
  var endpoint = caja.getAttribute("data-med-url");
  var rol = caja.getAttribute("data-med-rol") || "estudiante";
  var pautaEstado = document.getElementById("med-pauta-estado");
  var pautaTexto = document.getElementById("med-pauta-texto");
  var glosEstado = document.getElementById("med-glos-estado");
  var glosLista = document.getElementById("med-glos-lista");
  if (!endpoint) return;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pintar(j) {
    var pauta = rol === "docente" ? j.pauta_docente : j.pauta_estudiante;
    if (pauta && pautaTexto) {
      pautaTexto.hidden = false;
      pautaTexto.textContent = pauta;
      if (pautaEstado) pautaEstado.hidden = true;
    } else if (pautaEstado) {
      pautaEstado.hidden = false;
      pautaEstado.textContent =
        j && j.estado === "sin_texto"
          ? "Cuando haya texto de la clase se generará la pauta."
          : "Aún no hay pauta para este tema.";
    }
    var items = Array.isArray(j.glosario) ? j.glosario : [];
    if (items.length && glosLista) {
      glosLista.hidden = false;
      glosLista.innerHTML = items
        .map(function (it) {
          return (
            "<li><strong>" +
            esc(it.termino) +
            "</strong> · " +
            esc(it.definicion) +
            "</li>"
          );
        })
        .join("");
      if (glosEstado) glosEstado.hidden = true;
    } else if (glosEstado) {
      glosEstado.hidden = false;
      glosEstado.textContent = items.length ? "" : "No hay términos extraídos para este tema.";
    }
  }

  fetch(endpoint, { headers: { Accept: "application/json" }, credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(pintar)
    .catch(function () {
      if (pautaEstado) pautaEstado.textContent = "No se pudo cargar la pauta ahora.";
      if (glosEstado) glosEstado.textContent = "No se pudo cargar el glosario ahora.";
    });
})();
