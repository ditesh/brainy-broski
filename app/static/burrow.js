// The practice burrow: tap it and the pet pops out; "Bye!" sends it back. When the solution is shown, the
// question is finished, so the answer controls are switched off.
(function () {
  "use strict";
  function sound(name) { if (window.BBSound) window.BBSound.play(name); }

  function setOut(box, out) {
    box.classList.toggle("out", out);
    var stage = box.querySelector(".burrow-stage"), panel = box.querySelector(".burrow-panel");
    stage.setAttribute("aria-expanded", out ? "true" : "false");
    panel.hidden = !out;
    var call = box.querySelector(".burrow-call");
    if (call) call.textContent = out ? "Ask me anything!" : "🐾 " + (box.dataset.name || "Your pet") + " is in the burrow. Tap for help!";
    if (out) {
      sound("jingle");
      var slot = box.querySelector(".pet-slot");
      if (slot && window.BBPets) window.BBPets.play(slot, "happy");
    }
  }

  function init() {
    document.querySelectorAll(".burrow-box").forEach(function (box) {
      var stage = box.querySelector(".burrow-stage");
      stage.addEventListener("click", function () { setOut(box, !box.classList.contains("out")); });
      stage.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOut(box, !box.classList.contains("out")); }
      });
      box.querySelector(".burrow-bye").addEventListener("click", function () { setOut(box, false); });
    });
  }

  document.addEventListener("bb-locked", function () {
    var form = document.getElementById("answer-form");
    if (!form) return;
    form.querySelectorAll("input:not([type=hidden]), button").forEach(function (el) { el.disabled = true; });
    document.querySelectorAll('.mcq-choice').forEach(function (el) { el.disabled = true; });
    var box = document.querySelector(".burrow-box"), next = box && box.dataset.next;
    if (next && !form.querySelector(".after-solution")) {
      var a = document.createElement("a");
      a.className = "button primary after-solution"; a.href = next; a.textContent = "Next question →";
      form.appendChild(a);
    }
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
