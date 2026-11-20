// Technique pets: eyes follow the pointer, tickle on click/tap/Enter, and big-moment animations.
(function () {
  "use strict";
  var DURATION = { happy: 1500, hatch: 3200, grow: 1700 };
  var CLASS = { happy: "happy", hatch: "hatching", grow: "evolving" };

  function sound(name) { if (name && window.BBSound) window.BBSound.play(name); }

  function play(el, kind) {
    var cls = CLASS[kind];
    if (!el || !cls) return;
    el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls);
    clearTimeout(el._playT);
    if (kind === "hatch") el._playT = setTimeout(function () { reveal(el); }, DURATION.hatch);
  }

  // After hatching, swap the egg for the creature that came out (a <template class="reveal"> next to it).
  function reveal(el) {
    el.classList.remove("hatching");
    var tpl = el.parentNode && el.parentNode.querySelector("template.reveal");
    if (!tpl) return;
    var svg = el.querySelector("svg");
    if (svg) svg.replaceWith(tpl.content.cloneNode(true));
    el.dataset.stage = tpl.dataset.stage || "baby";
    if (tpl.dataset.name) el.setAttribute("aria-label", tpl.dataset.name);
    if (tpl.dataset.say) el.dataset.say = tpl.dataset.say;
    play(el, "happy");
  }

  // A buddy with lines says the next one in its speech bubble instead of the little pop-up.
  function talk(el) {
    var lines;
    try { lines = JSON.parse(el.dataset.lines || "[]"); } catch (e) { lines = []; }
    var speech = el.parentNode && el.parentNode.querySelector(".speech");
    if (!lines.length || !speech) return false;
    el._line = ((el._line || 0) + 1) % lines.length;
    speech.textContent = lines[el._line];
    speech.classList.remove("pop"); void speech.offsetWidth; speech.classList.add("pop");
    return true;
  }

  function tickle(el) {
    if (talk(el)) {
      el.classList.remove("tickled"); void el.offsetWidth; el.classList.add("tickled");
      clearTimeout(el._tickleT);
      el._tickleT = setTimeout(function () { el.classList.remove("tickled"); }, 800);
      sound("squeak");
      return;
    }
    var b = el.querySelector(".bubble");
    if (b) b.textContent = el.dataset.say || "hehe!";
    el.classList.remove("tickled"); void el.offsetWidth; el.classList.add("tickled");
    clearTimeout(el._tickleT);
    el._tickleT = setTimeout(function () { el.classList.remove("tickled"); }, 1300);
    sound("squeak");
  }

  var pending = null, queued = false;
  document.addEventListener("pointermove", function (e) {
    pending = e;
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () {
      queued = false;
      var ev = pending;
      document.querySelectorAll(".pet-slot").forEach(function (slot) {
        var svg = slot.querySelector("svg");
        if (!svg) return;
        var r = svg.getBoundingClientRect();
        if (!r.width) return;
        var dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height * 0.5);
        var d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 300) * 4;
        slot.querySelectorAll(".pupils").forEach(function (p) {
          p.style.transform = "translate(" + (dx / d * k).toFixed(1) + "px," + (dy / d * k).toFixed(1) + "px)";
        });
      });
    });
  }, { passive: true });

  document.addEventListener("click", function (e) {
    var slot = e.target.closest && e.target.closest(".pet-slot[role=button]");
    if (slot) tickle(slot);
  });
  document.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches(".pet-slot[role=button]")) {
      e.preventDefault();
      tickle(e.target);
    }
  });

  // Elements with data-play animate one after another when the page opens.
  function playQueued() {
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-play]"));
    var t = 400;
    items.forEach(function (el) {
      setTimeout(function () { play(el, el.dataset.play); sound(el.dataset.sound); }, t);
      t += (DURATION[el.dataset.play] || 1200) + 300;
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", playQueued);
  else playQueued();

  window.BBPets = { play: play, tickle: tickle };
})();
