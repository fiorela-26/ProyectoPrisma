(function () {
  var aviso = document.getElementById("aviso-offline");
  var DB = "prisma";
  var VER = 1;

  function abrirDb() {
    return new Promise(function (res, rej) {
      var r = indexedDB.open(DB, VER);
      r.onupgradeneeded = function () {
        var db = r.result;
        if (!db.objectStoreNames.contains("cola")) db.createObjectStore("cola", { keyPath: "id", autoIncrement: true });
        if (!db.objectStoreNames.contains("sesiones")) db.createObjectStore("sesiones");
      };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
  }

  function txStore(nombre, modo, fn) {
    return abrirDb().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction(nombre, modo);
        var st = tx.objectStore(nombre);
        var req = fn(st);
        tx.oncomplete = function () { res(req && "result" in req ? req.result : undefined); };
        tx.onerror = function () { rej(tx.error); };
        if (req) {
          req.onsuccess = function () { /* result leído en complete */ };
          req.onerror = function () { rej(req.error); };
        }
      });
    });
  }

  function encolar(payload) {
    return abrirDb().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction("cola", "readwrite");
        tx.objectStore("cola").add({ payload: payload, creado: Date.now() });
        tx.oncomplete = function () { res(); };
        tx.onerror = function () { rej(tx.error); };
      });
    });
  }

  function vaciar() {
    if (!navigator.onLine) return Promise.resolve();
    return abrirDb().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction("cola", "readonly");
        var req = tx.objectStore("cola").getAll();
        req.onsuccess = function () { res(req.result || []); };
        req.onerror = function () { rej(req.error); };
      }).then(function (filas) {
        var cadena = Promise.resolve();
        filas.forEach(function (fila) {
          cadena = cadena.then(function () {
            return fetch("/estudiante/interacciones", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(fila.payload),
              keepalive: true,
            }).then(function (r) {
              if (!(r.ok || r.status === 204)) return;
              return new Promise(function (res2, rej2) {
                var tx2 = db.transaction("cola", "readwrite");
                tx2.objectStore("cola").delete(fila.id);
                tx2.oncomplete = function () { res2(); };
                tx2.onerror = function () { rej2(tx2.error); };
              });
            }).catch(function () {});
          });
        });
        return cadena;
      });
    }).catch(function () {});
  }

  function enviar(payload) {
    var blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    if (navigator.onLine && navigator.sendBeacon && navigator.sendBeacon("/estudiante/interacciones", blob)) {
      return;
    }
    if (navigator.onLine) {
      fetch("/estudiante/interacciones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(function () { encolar(payload); });
      return;
    }
    encolar(payload);
  }

  function guardarSesion(id, datos) {
    return abrirDb().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction("sesiones", "readwrite");
        tx.objectStore("sesiones").put(datos, id);
        tx.oncomplete = function () { res(); };
        tx.onerror = function () { rej(tx.error); };
      });
    }).catch(function () {});
  }

  window.PrismaCola = { enviar: enviar, vaciar: vaciar, guardarSesion: guardarSesion };

  function syncEstado() {
    if (!aviso) return;
    aviso.hidden = navigator.onLine;
  }
  window.addEventListener("online", function () {
    syncEstado();
    vaciar();
  });
  window.addEventListener("offline", syncEstado);
  syncEstado();
  vaciar();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/service-worker.js").catch(function () {});
  }

  var partes = location.pathname.split("/").filter(Boolean);
  var enSesion = partes[0] === "estudiante" && partes[1] === "sesiones" && partes[2];
  if (!enSesion) return;
  var sesionId = partes[2];
  var t0 = Date.now();
  var enviado = false;

  var nodo = document.getElementById("paquetes-json");
  if (nodo) {
    try {
      guardarSesion(sesionId, { paquetes: JSON.parse(nodo.textContent || "[]"), guardado: Date.now() });
    } catch (e) {}
  }

  function payload(completado) {
    var chk = document.querySelector("input[name=activos]:checked");
    var done = document.getElementById("marcar-completado");
    return {
      sesion_id: sesionId,
      formato: chk ? chk.value : null,
      duracion_segundos: Math.max(0, Math.round((Date.now() - t0) / 1000)),
      completado: !!(completado || (done && done.checked)),
    };
  }

  function flush(forzarCompletado) {
    if (enviado && !forzarCompletado) return;
    enviado = true;
    enviar(payload(forzarCompletado));
  }

  var done = document.getElementById("marcar-completado");
  if (done) {
    done.addEventListener("change", function () {
      if (done.checked) enviar(payload(true));
    });
  }
  window.addEventListener("pagehide", function () { flush(false); });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush(false);
  });
})();
