(function () {
  if (window.self !== window.top) {
    document.documentElement.classList.add("da-embedded");
  }
  var el = document.getElementById("diapason-agent-config");
  if (!el || !el.textContent) {
    return;
  }
  try {
    window.DIAPASON_AGENT_CONFIG = JSON.parse(el.textContent);
  } catch (_e) {
    /* ignore malformed embed config */
  }
})();
