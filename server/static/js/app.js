(function () {
  // ---- Category radio -> reveal the drone-only fields ----
  const droneFields = document.getElementById("drone-fields");
  function syncDrone() {
    const drone = document.getElementById("cat-drone");
    const open = !!(drone && drone.checked);
    if (droneFields) droneFields.setAttribute("data-open", open ? "true" : "false");
  }
  document.querySelectorAll("input[name='category']").forEach((radio) => {
    radio.addEventListener("change", syncDrone);
  });
  syncDrone();

  // ---- Error-state shake (transitions-dev) ----
  const cs = getComputedStyle(document.documentElement);
  const ms = (name, fallback) => {
    const v = parseFloat(cs.getPropertyValue(name));
    return Number.isFinite(v) ? v : fallback;
  };
  function showError(wrapId) {
    const wrap = document.getElementById(wrapId);
    if (!wrap) return;
    const input = wrap.querySelector(".t-input") || wrap;
    wrap.classList.add("is-error");
    input.classList.add("is-error");
    input.classList.remove("is-shaking");
    void input.offsetWidth; // reflow so the shake replays
    input.classList.add("is-shaking");
    const shakeMs = ms("--shake-dur-a", 80) * 2 + ms("--shake-dur-b", 60) * 2;
    setTimeout(() => input.classList.remove("is-shaking"), shakeMs + 20);
    if (wrap._revertTimer) clearTimeout(wrap._revertTimer);
    wrap._revertTimer = setTimeout(() => {
      wrap._revertTimer = null;
      wrap.classList.remove("is-error");
      input.classList.remove("is-error");
    }, shakeMs + ms("--revert-hold", 3000));
  }
  // Typing clears the error treatment immediately.
  document.querySelectorAll(".t-input-wrap input").forEach((el) => {
    el.addEventListener("input", () => {
      const wrap = el.closest(".t-input-wrap");
      if (!wrap) return;
      const input = wrap.querySelector(".t-input");
      wrap.classList.remove("is-error");
      if (input) input.classList.remove("is-error");
    });
  });

  function validateAddForm() {
    let ok = true;
    const label = document.getElementById("label");
    if (label && !label.value.trim()) {
      showError("label-wrap");
      ok = false;
    }
    const hasFiles = (id) => {
      const el = document.getElementById(id);
      return !!(el && el.files && el.files.length > 0);
    };
    if (!hasFiles("audio_files") && !hasFiles("video_files") && !hasFiles("label_image")) {
      showError("files-wrap");
      ok = false;
    }
    return ok;
  }

  // ---- Submit: validate the add form, then show the busy state ----
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.id === "add-form" && !validateAddForm()) {
        event.preventDefault();
        return;
      }
      if (event.defaultPrevented) return; // e.g. a cancelled confirm()
      const button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.dataset.originalText = button.textContent || "";
        button.textContent = "Обработка...";
      }
    });
  });

  // ---- Success check once training has produced an accuracy estimate ----
  const accuracyCard = document.getElementById("accuracy-card");
  const check = document.getElementById("train-check");
  if (accuracyCard && check) {
    check.setAttribute("data-state", "out");
    void check.offsetWidth;
    check.setAttribute("data-state", "in");
  }
})();
