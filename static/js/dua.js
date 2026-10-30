(function (global) {
  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bloques(texto) {
    var t = String(texto || "").trim();
    if (!t) return [];
    var partes = t.split(/\n(?=##\s)/);
    if (partes.length < 2) {
      partes = t.split(/\n\s*\n/).filter(function (p) { return p.trim().length > 20; });
    }
    if (!partes.length) partes = [t];
    return partes.map(function (p) { return p.trim(); });
  }

  function bionicHtml(texto) {
    return esc(texto).replace(/\S+/g, function (w) {
      var n = Math.max(1, Math.ceil(w.length * 0.4));
      return "<strong>" + w.slice(0, n) + "</strong>" + w.slice(n);
    });
  }

  function pills(texto) {
    return "<ol class='pildoras'>" + bloques(texto).map(function (p) {
      var lineas = p.split("\n");
      var tit = lineas[0].replace(/^#+\s*/, "");
      var cuerpo = lineas.slice(1).join(" ").trim() || tit;
      return "<li><h3>" + esc(tit) + "</h3><p>" + bionicHtml(cuerpo) + "</p></li>";
    }).join("") + "</ol>";
  }

  function mapa(texto) {
    return "<div class='dua-mapa' role='list'>" + bloques(texto).map(function (p, i) {
      var tit = p.split("\n")[0].replace(/^#+\s*/, "");
      return "<article class='dua-nodo' role='listitem'><span class='chip'>" + (i + 1) + "</span><h3>" + esc(tit.slice(0, 90)) + "</h3></article>";
    }).join("") + "</div>";
  }

  function seleccion(root) {
    return Array.prototype.map.call(root.querySelectorAll("[data-dua]:checked"), function (el) {
      return el.value;
    });
  }

  function vocesListas() {
    if (!global.speechSynthesis) return [];
    return global.speechSynthesis.getVoices() || [];
  }

  function ttsSoporta(codigo) {
    if (!global.speechSynthesis) return false;
    var pref = String(codigo || "").toLowerCase();
    if (!pref) return false;
    var base = pref.split("-")[0];
    var voces = vocesListas();
    if (!voces.length) {
      return ["es", "en", "fr", "pt", "de", "it", "zh", "ja", "ko", "ru", "nl"].indexOf(base) >= 0;
    }
    return voces.some(function (v) {
      var lang = String(v.lang || "").toLowerCase();
      return lang === pref || lang.indexOf(base + "-") === 0 || lang === base;
    });
  }

  function avisoAudio(nombre) {
    return (
      '<p class="aviso" role="status">El contenido ha sido traducido con éxito a ' +
      esc(nombre) +
      ", pero la reproducción de voz en audio aún no está disponible para esta lengua.</p>"
    );
  }

  function setReproductorEstado(contenedor, estado) {
    if (!contenedor) return;
    var idle = estado === "idle";
    var playing = estado === "playing";
    var paused = estado === "paused";
    function vis(sel, show) {
      var el = contenedor.querySelector(sel);
      if (el) el.hidden = !show;
    }
    vis("[data-dua-hablar]", idle);
    vis("[data-dua-pausar]", playing);
    vis("[data-dua-continuar]", paused);
    vis("[data-dua-parar]", playing || paused);
  }

  function reproductor() {
    return (
      '<div class="dua-audio">' +
      '<button type="button" class="btn p" data-dua-hablar>Escuchar narración</button>' +
      '<button type="button" class="btn" data-dua-pausar hidden>Pausar</button>' +
      '<button type="button" class="btn p" data-dua-continuar hidden>Continuar</button>' +
      '<button type="button" class="btn d" data-dua-parar hidden>Detener</button>' +
      '<span class="mut">Pausa para seguir donde lo dejaste; detener reinicia la narración.</span></div>'
    );
  }

  function aplicar(preview, texto, needs, meta) {
    parar();
    preview.setAttribute("data-dua", needs.join(" "));
    if (!texto) {
      preview.innerHTML = "<p class='mut'>Aún no hay texto de la clase.</p>";
      return;
    }
    meta = meta || {};
    var html = "";
    if (meta.error) {
      html += '<p class="aviso err" role="alert">' + esc(meta.error) + "</p>";
    }
    var quiereAudio = needs.indexOf("ceguera") >= 0 || needs.indexOf("lengua") >= 0;
    var traducido = !!meta.traducido;
    if (quiereAudio && !meta.error) {
      if (meta.tts) html += reproductor();
      else if (traducido && meta.nombre) html += avisoAudio(meta.nombre);
      else if (needs.indexOf("ceguera") >= 0 && meta.tts !== false) html += reproductor();
      else if (needs.indexOf("ceguera") >= 0 && meta.tts === false) html += avisoAudio(meta.nombre || "este idioma");
    }
    if (needs.indexOf("apoyo_visual") >= 0) html += mapa(texto);
    if (needs.indexOf("tdah") >= 0) html += pills(texto);
    else html += "<div class='texto'>" + esc(texto) + "</div>";
    preview.innerHTML = html;
  }

  function parar() {
    if (!global.speechSynthesis) return;
    global.speechSynthesis.cancel();
  }

  function pausar() {
    if (!global.speechSynthesis) return false;
    if (global.speechSynthesis.speaking && !global.speechSynthesis.paused) {
      global.speechSynthesis.pause();
      return true;
    }
    return false;
  }

  function continuar() {
    if (!global.speechSynthesis) return false;
    if (global.speechSynthesis.paused) {
      global.speechSynthesis.resume();
      return true;
    }
    return false;
  }

  function hablar(texto, lang, alTerminar) {
    if (!global.speechSynthesis) return false;
    parar();
    var u = new SpeechSynthesisUtterance(texto);
    u.lang = lang || "es-PE";
    var voces = vocesListas();
    var pref = String(lang || "").toLowerCase();
    var base = pref.split("-")[0];
    var voz = voces.filter(function (v) {
      var l = String(v.lang || "").toLowerCase();
      return l === pref || l.indexOf(base) === 0;
    })[0];
    if (voz) u.voice = voz;
    u.onend = function () {
      if (alTerminar) alTerminar();
    };
    u.onerror = function () {
      if (alTerminar) alTerminar();
    };
    global.speechSynthesis.speak(u);
    return true;
  }

  function estadoIdioma(root, tipo, msg) {
    var el = root.querySelector("[data-dua-idioma-estado]");
    if (!el) return;
    if (!msg) {
      el.hidden = true;
      el.textContent = "";
      el.className = "aviso";
      el.removeAttribute("role");
      return;
    }
    el.hidden = false;
    el.textContent = msg;
    el.className = "aviso" + (tipo === "error" ? " err" : "");
    el.setAttribute("role", tipo === "error" ? "alert" : "status");
  }

  function init(opts) {
    var root = typeof opts.root === "string" ? document.querySelector(opts.root) : opts.root;
    var preview = typeof opts.preview === "string" ? document.querySelector(opts.preview) : opts.preview;
    if (!root || !preview) return;
    var original = opts.texto || "";
    var textoMostrado = original;
    var ultimoMeta = { tts: ttsSoporta("es-PE"), codigo: "es-PE", traducido: false, nombre: "Español" };
    var pendiente = false;

    function idioma() {
      var sel = root.querySelector("[data-dua-idioma]");
      return sel && sel.value ? sel.value.trim() : "";
    }

    function codigoVoz() {
      return (ultimoMeta && ultimoMeta.codigo) || "es-PE";
    }

    function clasesCuerpo(needs) {
      if (!opts.aplicarCuerpo) return;
      Array.prototype.slice.call(document.body.classList).forEach(function (c) {
        if (c.indexOf("dua-") === 0) document.body.classList.remove(c);
      });
      needs.forEach(function (n) {
        document.body.classList.add("dua-" + n);
      });
    }

    function pintarVista() {
      var needs = seleccion(root);
      clasesCuerpo(needs);
      if (needs.indexOf("lengua") < 0) {
        textoMostrado = original;
        ultimoMeta = { tts: ttsSoporta("es-PE"), codigo: "es-PE", traducido: false, nombre: "Español" };
        estadoIdioma(root, "", "");
      }
      aplicar(preview, textoMostrado, needs, ultimoMeta);
    }

    function aplicarIdioma() {
      var needs = seleccion(root);
      var dest = idioma();
      if (dest.length < 2) {
        var errCorto = "El idioma ingresado no fue reconocido o no es válido. Por favor, verifica el nombre.";
        estadoIdioma(root, "error", errCorto);
        ultimoMeta = { error: errCorto, tts: false, traducido: false };
        textoMostrado = original;
        aplicar(preview, textoMostrado, needs, ultimoMeta);
        return;
      }
      if (!opts.traducirUrl || pendiente) return;
      pendiente = true;
      estadoIdioma(root, "ok", "Identificando el idioma y traduciendo el texto extraído…");
      preview.setAttribute("aria-busy", "true");
      fetch(opts.traducirUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ idioma: dest }),
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return j || {};
          });
        })
        .then(function (j) {
          pendiente = false;
          preview.setAttribute("aria-busy", "false");
          if (!j.valido) {
            var msg = j.error || "El idioma ingresado no fue reconocido o no es válido. Por favor, verifica el nombre.";
            estadoIdioma(root, "error", msg);
            ultimoMeta = { error: msg, tts: false, traducido: false, nombre: dest };
            textoMostrado = original;
            aplicar(preview, textoMostrado, seleccion(root), ultimoMeta);
            return;
          }
          var nombre = j.nombre || dest;
          var codigo = j.codigo || "es-PE";
          var iaAudio = j.audio !== false;
          var hayVoz = iaAudio && ttsSoporta(codigo);
          ultimoMeta = { traducido: true, nombre: nombre, codigo: codigo, tts: hayVoz };
          textoMostrado = j.texto || original;
          if (hayVoz) {
            estadoIdioma(root, "", "Texto traducido a " + nombre + ". Ya puedes escuchar la narración.");
          } else {
            estadoIdioma(
              root,
              "ok",
              "El contenido ha sido traducido con éxito a " +
                nombre +
                ", pero la reproducción de voz en audio aún no está disponible para esta lengua."
            );
          }
          aplicar(preview, textoMostrado, seleccion(root), ultimoMeta);
        })
        .catch(function () {
          pendiente = false;
          preview.setAttribute("aria-busy", "false");
          estadoIdioma(root, "error", "No se pudo comprobar el idioma. Inténtalo de nuevo.");
        });
    }

    root.addEventListener("change", function (ev) {
      if (ev.target && ev.target.getAttribute("data-dua-idioma") != null) return;
      pintarVista();
    });
    var btnAplicar = root.querySelector("[data-dua-aplicar]");
    if (btnAplicar) {
      btnAplicar.addEventListener("click", function (ev) {
        ev.preventDefault();
        aplicarIdioma();
      });
    }
    var campoIdioma = root.querySelector("[data-dua-idioma]");
    if (campoIdioma) {
      campoIdioma.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          aplicarIdioma();
        }
      });
    }
    preview.addEventListener("click", function (ev) {
      var cajaAudio = ev.target.closest(".dua-audio");
      if (!cajaAudio) return;
      if (ev.target.closest("[data-dua-parar]")) {
        parar();
        setReproductorEstado(cajaAudio, "idle");
        return;
      }
      if (ev.target.closest("[data-dua-pausar]")) {
        if (pausar()) setReproductorEstado(cajaAudio, "paused");
        return;
      }
      if (ev.target.closest("[data-dua-continuar]")) {
        if (continuar()) setReproductorEstado(cajaAudio, "playing");
        return;
      }
      var btn = ev.target.closest("[data-dua-hablar]");
      if (!btn) return;
      if (!ultimoMeta.tts || !ttsSoporta(codigoVoz())) {
        estadoIdioma(
          root,
          "ok",
          "El contenido ha sido traducido con éxito a " +
            (ultimoMeta.nombre || "este idioma") +
            ", pero la reproducción de voz en audio aún no está disponible para esta lengua."
        );
        return;
      }
      var nodoTexto = preview.querySelector(".texto") || preview.querySelector(".pildoras") || preview;
      setReproductorEstado(cajaAudio, "playing");
      hablar(nodoTexto.textContent || textoMostrado, codigoVoz(), function () {
        setReproductorEstado(cajaAudio, "idle");
      });
    });
    pintarVista();
  }

  global.PrismaDUA = {
    init: init,
    hablar: hablar,
    parar: parar,
    pausar: pausar,
    continuar: continuar,
    setReproductorEstado: setReproductorEstado,
    ttsSoporta: ttsSoporta,
  };
})(window);
