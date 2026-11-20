// Brain-break games: Stone Duel (Nim) against his buddy, and Target 24. Results go back to the server once.
(function () {
  "use strict";

  function sound(name) { if (window.BBSound) window.BBSound.play(name); }

  function store(key, val) {
    try { if (val === undefined) return window.localStorage.getItem(key); window.localStorage.setItem(key, val); }
    catch (e) { return null; }
  }

  function setup(game) {
    var speech = game.querySelector(".speech"), slot = game.querySelector(".pet-slot");
    var who = speech ? speech.dataset.opponent : "Robo";
    var done = false;

    function say(text) {
      if (!speech) return;
      speech.textContent = text;
      speech.classList.remove("pop"); void speech.offsetWidth; speech.classList.add("pop");
    }

    function finish(won, text) {
      if (done) return;
      done = true;
      game.classList.add(won ? "won" : "lost");
      game.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      var over = game.querySelector(".game-over");
      over.querySelector(".game-over-text").textContent = text;
      over.hidden = false;
      if (won) { sound("fanfare"); } else { sound("squeak"); }
      if (slot && window.BBPets) window.BBPets.play(slot, "happy");
      var round = game.dataset.round;
      if (round) {
        var body = new URLSearchParams({ won: won ? "1" : "0" });
        fetch("/games/plays/" + round + "/result", { method: "POST", body: body, credentials: "same-origin" });
      }
    }

    return { say: say, finish: finish, who: who, isDone: function () { return done; } };
  }

  // ---- Stone Duel: take 1-3, last stone wins. The buddy plays the winning move most of the time. ----
  function nim(game) {
    var ui = setup(game);
    var left = parseInt(game.dataset.pile, 10);
    var pile = game.querySelector(".nim-pile"), count = game.querySelector(".nim-left");
    var buttons = game.querySelectorAll("[data-take]");
    var SMART = 0.7;
    var losses = parseInt(store("bb-nim-losses") || "0", 10);
    if (losses >= 2) ui.say("Psst… try to leave me a multiple of 4. 🤫");

    function draw() {
      count.textContent = left;
      pile.innerHTML = "";
      for (var i = 0; i < left; i++) {
        var s = document.createElement("span");
        s.className = "stone";
        pile.appendChild(s);
      }
      buttons.forEach(function (b) { b.disabled = ui.isDone() || parseInt(b.dataset.take, 10) > left; });
    }

    function buddyMove() {
      var take = left % 4;
      if (take === 0 || Math.random() > SMART) take = 1 + Math.floor(Math.random() * Math.min(3, left));
      left -= take;
      ui.say(ui.who + " takes " + take + ".");
      draw();
      if (left === 0) {
        store("bb-nim-losses", String(losses + 1));
        ui.finish(false, ui.who + " took the last stone. Rematch next brain break!");
      }
    }

    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        var take = parseInt(b.dataset.take, 10);
        if (ui.isDone() || take > left) return;
        left -= take;
        sound("ding");
        draw();
        if (left === 0) {
          store("bb-nim-losses", "0");
          ui.finish(true, "You took the last stone — you win! 🏆");
          return;
        }
        buttons.forEach(function (x) { x.disabled = true; });
        ui.say("Hmm, let me think…");
        setTimeout(buddyMove, 800);
      });
    });
    draw();
  }

  // ---- Target 24: join two tiles with an operation until one tile is left. Exact fractions. ----
  function gcd(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { var t = b; b = a % b; a = t; } return a || 1; }
  function frac(n, d) { var g = gcd(n, d); if (d < 0) { n = -n; d = -d; } return { n: n / g, d: d / g }; }
  function label(f) { return f.d === 1 ? String(f.n) : f.n + "/" + f.d; }
  var OPS = {
    "+": function (a, b) { return frac(a.n * b.d + b.n * a.d, a.d * b.d); },
    "−": function (a, b) { return frac(a.n * b.d - b.n * a.d, a.d * b.d); },
    "×": function (a, b) { return frac(a.n * b.n, a.d * b.d); },
    "÷": function (a, b) { return b.n === 0 ? null : frac(a.n * b.d, a.d * b.n); },
  };

  function target(game) {
    var ui = setup(game);
    var goal = parseInt(game.dataset.target, 10);
    var start = JSON.parse(game.dataset.numbers).map(function (n) { return frac(n, 1); });
    var tiles = start.slice(), history = [], steps = [];
    var picked = null, op = null;
    var box = game.querySelector(".tiles"), stepsEl = game.querySelector(".target-steps");
    var opButtons = game.querySelectorAll("[data-op]");

    function draw() {
      box.innerHTML = "";
      tiles.forEach(function (t, i) {
        var b = document.createElement("button");
        b.className = "tile" + (i === picked ? " picked" : "");
        b.textContent = label(t);
        b.setAttribute("aria-pressed", i === picked ? "true" : "false");
        b.disabled = ui.isDone();
        b.addEventListener("click", function () { tap(i); });
        box.appendChild(b);
      });
      opButtons.forEach(function (b) {
        b.classList.toggle("picked", b.dataset.op === op);
        b.disabled = ui.isDone() || picked === null;
      });
      stepsEl.textContent = steps.join("   ·   ");
    }

    function tap(i) {
      if (picked === null || op === null) { picked = (picked === i ? null : i); op = null; draw(); return; }
      if (i === picked) { picked = null; op = null; draw(); return; }
      var a = tiles[picked], b = tiles[i], r = OPS[op](a, b);
      if (r === null) { ui.say("Dividing by zero? Even I can't do that! 😅"); return; }
      history.push({ tiles: tiles.slice(), steps: steps.slice() });
      steps.push(label(a) + " " + op + " " + label(b) + " = " + label(r));
      var next = tiles.filter(function (_, k) { return k !== picked && k !== i; });
      next.push(r);
      tiles = next; picked = tiles.length - 1; op = null;
      sound("ding");
      if (tiles.length === 1) {
        picked = null;
        if (r.d === 1 && r.n === goal) {
          draw();
          ui.finish(true, "You made " + goal + "! Brilliant! 🏆");
          return;
        }
        ui.say("That makes " + label(r) + ", not " + goal + ". Try Undo!");
      }
      draw();
    }

    opButtons.forEach(function (b) {
      b.addEventListener("click", function () { if (picked !== null) { op = b.dataset.op; draw(); } });
    });
    game.querySelector("[data-undo]").addEventListener("click", function () {
      var h = history.pop();
      if (h) { tiles = h.tiles; steps = h.steps; picked = null; op = null; draw(); }
    });
    game.querySelector("[data-reset]").addEventListener("click", function () {
      tiles = start.slice(); history = []; steps = []; picked = null; op = null; draw();
    });
    game.querySelector("[data-giveup]").addEventListener("click", function () {
      ui.finish(false, "One way: " + game.dataset.answer + " = " + goal + ". You'll get the next one!");
      draw();
    });
    draw();
  }

  function init() {
    document.querySelectorAll('.game[data-game="nim"]').forEach(nim);
    document.querySelectorAll('.game[data-game="target"]').forEach(target);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
