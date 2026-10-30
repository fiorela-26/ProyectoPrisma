(function () {
  function bionic(el) {
    el.innerHTML = el.textContent.replace(/\S+/g, function (w) {
      var n = Math.max(1, Math.ceil(w.length * 0.4));
      return "<strong>" + w.slice(0, n) + "</strong>" + w.slice(n);
    });
  }
  document.querySelectorAll(".bionic").forEach(bionic);

  var form = document.getElementById("form-chat");
  if (!form) return;
  var log = document.getElementById("chat-log");
  var estado = document.getElementById("chat-estado");
  var pregunta = document.getElementById("pregunta");
  var sesionId = location.pathname.split("/").filter(Boolean).pop();
  var cajaTts = document.getElementById("tts-tutor");

  function setTtsEstado(s) {
    if (window.PrismaDUA && window.PrismaDUA.setReproductorEstado && cajaTts) {
      window.PrismaDUA.setReproductorEstado(cajaTts, s);
    }
  }

  function textoUltimaRespuesta() {
    var ps = log.querySelectorAll(".msg");
    var ultimo = ps[ps.length - 1];
    return ultimo ? ultimo.textContent : "";
  }

  function agregar(quien, texto) {
    var p = document.createElement("div");
    p.className = "msg" + (quien === "Tú" ? " u" : "");
    p.appendChild(document.createTextNode(texto));
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
    return p;
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = (pregunta.value || "").trim();
    if (!q) return;
    agregar("Tú", q);
    pregunta.value = "";
    estado.textContent = "El tutor está escribiendo…";
    log.setAttribute("aria-busy", "true");
    var nodo = agregar("Tutor", "");
    fetch("/chat/" + sesionId, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ pregunta: q }),
    }).then(function (resp) {
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";
      function leer() {
        return reader.read().then(function (r) {
          buf += decoder.decode(r.value || new Uint8Array(), { stream: !r.done });
          var partes = buf.split("\n\n");
          buf = partes.pop();
          partes.forEach(function (bloque) {
            var lineas = bloque.split("\n");
            var evento = "message";
            var data = [];
            lineas.forEach(function (ln) {
              if (ln.indexOf("event:") === 0) evento = ln.slice(6).trim();
              if (ln.indexOf("data:") === 0) data.push(ln.slice(5).trim());
            });
            var payload = data.join("\n");
            if (evento === "error") {
              estado.textContent = payload;
              log.setAttribute("aria-busy", "false");
              return;
            }
            if (evento === "done") {
              estado.textContent = "Respuesta lista. Es una IA y puede equivocarse.";
              log.setAttribute("aria-busy", "false");
              return;
            }
            try {
              nodo.appendChild(document.createTextNode(JSON.parse(payload)));
            } catch (e) {
              nodo.appendChild(document.createTextNode(payload));
            }
            log.scrollTop = log.scrollHeight;
          });
          if (!r.done) return leer();
        });
      }
      return leer();
    }).catch(function () {
      estado.textContent = "El tutor requiere conexión a internet.";
      log.setAttribute("aria-busy", "false");
    });
  });

  document.getElementById("btn-duda").addEventListener("click", function () {
    var q = (pregunta.value || "").trim();
    if (!q) {
      estado.textContent = "Escribe la duda antes de enviarla.";
      return;
    }
    fetch("/chat/" + sesionId + "/duda", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta: q }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      estado.textContent = j.mensaje || j.error || "Listo.";
    });
  });

  var rec;
  document.getElementById("btn-voz").addEventListener("click", function () {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      estado.textContent = "Tu navegador no permite dictado.";
      return;
    }
    var btnVoz = document.getElementById("btn-voz");
    rec = rec || new SR();
    rec.lang = "es-PE";
    rec.onresult = function (e) {
      pregunta.value = (pregunta.value + " " + e.results[0][0].transcript).trim();
    };
    rec.onend = function () {
      if (btnVoz) btnVoz.setAttribute("aria-pressed", "false");
      estado.textContent = "Dictado listo.";
    };
    rec.start();
    if (btnVoz) btnVoz.setAttribute("aria-pressed", "true");
    estado.textContent = "Escuchando…";
  });

  if (cajaTts) {
    cajaTts.addEventListener("click", function (ev) {
      var tts = window.PrismaDUA;
      if (!tts || !window.speechSynthesis) return;
      if (ev.target.closest("[data-dua-parar]")) {
        tts.parar();
        setTtsEstado("idle");
        estado.textContent = "Lectura detenida.";
        return;
      }
      if (ev.target.closest("[data-dua-pausar]")) {
        if (tts.pausar()) {
          setTtsEstado("paused");
          estado.textContent = "Pausado. Pulsa Continuar para seguir donde lo dejaste.";
        }
        return;
      }
      if (ev.target.closest("[data-dua-continuar]")) {
        if (tts.continuar()) {
          setTtsEstado("playing");
          estado.textContent = "Reproduciendo…";
        }
        return;
      }
      if (!ev.target.closest("[data-dua-hablar]")) return;
      var texto = textoUltimaRespuesta();
      if (!texto) {
        estado.textContent = "Aún no hay respuesta del tutor para escuchar.";
        return;
      }
      setTtsEstado("playing");
      tts.hablar(texto, "es-PE", function () {
        setTtsEstado("idle");
        estado.textContent = "Lectura terminada.";
      });
      estado.textContent = "Reproduciendo la última respuesta…";
    });
  }
})();
