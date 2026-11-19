// Brainy Broski sounds, made in the browser with Web Audio (no files). Silent when <body data-sound-pref="off">.
(function () {
  "use strict";
  var ctx = null, queued = null, queuedAt = 0;
  var QUEUE_MS = 4000;  // a sound waiting for a tap is dropped after this, so it never plays out of place

  function enabled() { return document.body && document.body.dataset.soundPref === "on"; }

  function audio() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    return ctx;
  }

  // One soft note: frequency (Hz), start offset and length (s), waveform, peak volume, optional slide target.
  function note(a, freq, at, len, type, vol, slideTo) {
    var t = a.currentTime + at, o = a.createOscillator(), g = a.createGain();
    o.type = type || "sine";
    o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + len);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol || 0.18, t + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, t + len);
    o.connect(g); g.connect(a.destination);
    o.start(t); o.stop(t + len + 0.05);
  }

  function noise(a, at, len, vol) {
    var n = Math.floor(a.sampleRate * len), buf = a.createBuffer(1, n, a.sampleRate), d = buf.getChannelData(0);
    for (var i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3);
    var s = a.createBufferSource(), g = a.createGain(), f = a.createBiquadFilter();
    f.type = "highpass"; f.frequency.value = 1800;
    s.buffer = buf; g.gain.value = vol || 0.25;
    s.connect(f); f.connect(g); g.connect(a.destination);
    s.start(a.currentTime + at);
  }

  var SOUNDS = {
    // a pet grew: bright two-note ding
    ding: function (a) { note(a, 1046.5, 0, 0.25, "sine", 0.2); note(a, 1568, 0.09, 0.4, "sine", 0.16); },
    // an egg cracks: two crunchy clicks and a little pop
    crack: function (a) { noise(a, 0, 0.06, 0.3); noise(a, 0.16, 0.08, 0.35); note(a, 660, 0.32, 0.18, "triangle", 0.2, 990); },
    // a pet grows up: rising arpeggio
    fanfare: function (a) {
      [523.3, 659.3, 784, 1046.5].forEach(function (f, i) { note(a, f, i * 0.12, 0.3, "triangle", 0.18); });
      note(a, 1318.5, 0.5, 0.7, "sine", 0.16);
    },
    // weekly goal met: happy jingle
    jingle: function (a) {
      [784, 988, 1175, 1568, 1175, 1568].forEach(function (f, i) { note(a, f, i * 0.1, 0.22, "square", 0.06); });
    },
    // tickle: a quick squeak
    squeak: function (a) { note(a, 900, 0, 0.16, "sine", 0.14, 1600); },
  };

  function play(name) {
    if (!enabled() || !SOUNDS[name]) return;
    var a = audio();
    if (!a) return;
    if (a.state === "suspended") {
      queued = name; queuedAt = Date.now();   // the browser waits for a tap; play it then if still fresh
      a.resume().then(function () {
        if (queued === name && a.state === "running" && Date.now() - queuedAt < QUEUE_MS) { queued = null; SOUNDS[name](a); }
      });
      return;
    }
    SOUNDS[name](a);
  }

  function unlock() {
    var a = enabled() && audio();
    if (!a || a.state !== "suspended") return;
    a.resume().then(function () {
      var q = queued, fresh = Date.now() - queuedAt < QUEUE_MS;
      queued = null;
      if (q && fresh) SOUNDS[q](a);
    });
  }
  document.addEventListener("pointerdown", unlock, { passive: true });
  document.addEventListener("keydown", unlock);

  window.BBSound = { play: play };
})();
