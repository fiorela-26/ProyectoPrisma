(function () {
  var caja = document.getElementById("imagen-educativa");
  if (!caja) return;
  var img = document.getElementById("img-edu");
  var estado = document.getElementById("img-edu-estado");
  var endpoint = caja.getAttribute("data-img-url");
  if (!endpoint || !img) return;
  if (document.body.classList.contains("dua-baja_vision")) {
    caja.classList.add("img-edu-contraste");
  }

  function mostrar(url, alt) {
    img.alt = alt || "Imagen educativa del tema";
    img.onload = function () {
      img.hidden = false;
      if (estado) estado.hidden = true;
    };
    img.onerror = function () {
      if (estado) {
        estado.hidden = false;
        estado.textContent = "No se pudo cargar la ilustración. Recarga la página para reintentar.";
      }
    };
    img.src = url;
  }

  fetch(endpoint, { headers: { Accept: "application/json" }, credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (j && j.url) {
        mostrar(j.url, j.alt);
        return;
      }
      if (estado) {
        if (j && j.estado === "sin_texto") {
          estado.textContent = "Cuando haya texto de la clase se generará la ilustración.";
        } else if (j && (j.error || j.estado === "error")) {
          estado.textContent = j.error || "No se pudo generar la ilustración. Revisa el servidor e inténtalo de nuevo.";
        } else {
          estado.textContent = "Aún no hay ilustración para este tema.";
        }
      }
    })
    .catch(function () {
      if (estado) estado.textContent = "No se pudo generar la ilustración ahora. Recarga la página.";
    });

  var form = document.getElementById("form-dua-sim") || document.getElementById("form-dua-est");
  if (form) {
    form.addEventListener("change", function () {
      var baja = form.querySelector('[data-dua="baja_vision"]:checked');
      caja.classList.toggle("img-edu-contraste", !!baja);
    });
  }
})();
