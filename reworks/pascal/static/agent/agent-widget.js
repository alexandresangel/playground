/**
 * Diapason Agent — host-page launcher (vanilla JS), Pascal branding.
 */
(function () {
  "use strict";

  var ROOT_ID = "diapason-agent-widget-root";
  var script =
    document.currentScript ||
    document.querySelector("script[src*='agent-widget.js']");

  function attr(name, fallback) {
    if (!script) return fallback;
    var v = script.getAttribute(name);
    return v !== null && v !== "" ? v : fallback;
  }

  function resolveUrl(relative) {
    if (!relative) return "/";
    if (/^https?:\/\//i.test(relative)) return relative;
    try {
      return new URL(relative, window.location.href).href;
    } catch (_e) {
      return relative;
    }
  }

  function scriptBase() {
    if (!script || !script.src) return "";
    return script.src.replace(/\/[^/]*$/, "/");
  }

  var chatUrl = resolveUrl(attr("data-chat-url", "/"));
  var placement = attr("data-placement", "fab");
  var mountSelector = attr("data-mount", "");
  var logoBase = scriptBase();
  var logoUrl = resolveUrl(attr("data-logo-url", logoBase + "logo-p.png"));
  var titleSub = attr("data-title-sub", "Diapason Agent");
  var ariaLabel = attr("data-aria-label", "Pascal - agent Diapason");
  var closeOnBackdrop = attr("data-close-on-backdrop", "true") !== "false";
  var maximizeContainerSelector = attr(
    "data-maximize-container",
    "#modules-container"
  );
  var zIndex = parseInt(attr("data-z-index", "2147483000"), 10) || 2147483000;

  if (document.getElementById(ROOT_ID)) {
    return;
  }

  function createLogoImg(alt, variant) {
    var img = document.createElement("img");
    img.className =
      "da-dia-logo-img" + (variant === "header" ? " da-dia-logo-img--header" : "");
    img.src = logoUrl;
    img.alt = alt || "Pascal";
    img.decoding = "async";
    return img;
  }

  function buildDiaLauncher() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "da-dia-btn da-widget-launcher" +
      (placement === "header" ? " da-dia-btn--header" : " da-dia-btn--fab");
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-controls", "da-widget-dialog");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", ariaLabel);
    btn.setAttribute("title", ariaLabel);
    btn.appendChild(createLogoImg(ariaLabel, "header"));
    return btn;
  }

  function buildRoot() {
    var el = document.createElement("div");
    el.id = ROOT_ID;
    el.className = "da-widget-root";
    el.setAttribute("data-da-widget", "1");

    var btn = buildDiaLauncher();

    var bd = document.createElement("div");
    bd.className = "da-widget-backdrop";
    bd.setAttribute("data-da-backdrop", "");
    bd.hidden = true;

    var dlg = document.createElement("div");
    dlg.id = "da-widget-dialog";
    dlg.className = "da-widget-dialog";
    dlg.setAttribute("role", "dialog");
    dlg.setAttribute("aria-modal", "true");
    dlg.setAttribute("aria-labelledby", "da-widget-title");
    dlg.hidden = true;

    var hdr = document.createElement("header");
    hdr.className = "da-widget-header";
    hdr.setAttribute("data-da-drag-handle", "");

    var hdrMain = document.createElement("div");
    hdrMain.className = "da-widget-header-main";

    var brand = document.createElement("div");
    brand.className = "da-widget-header-brand";
    brand.appendChild(createLogoImg("Pascal", "dialog"));

    var titleBlock = document.createElement("div");
    titleBlock.className = "da-widget-title-block";
    var h2 = document.createElement("h2");
    h2.id = "da-widget-title";
    h2.className = "da-widget-title";
    h2.textContent = titleSub;
    titleBlock.appendChild(h2);

    var actions = document.createElement("div");
    actions.className = "da-widget-header-actions";
    var maximize = document.createElement("button");
    maximize.type = "button";
    maximize.className = "da-widget-icon-btn";
    maximize.setAttribute("data-da-maximize", "");
    maximize.setAttribute("aria-label", "Maximize");
    maximize.setAttribute("title", "Maximize");
    var maxGlyph = document.createElement("span");
    maxGlyph.className =
      "da-widget-icon-glyph da-widget-icon-glyph--maximize";
    maxGlyph.setAttribute("aria-hidden", "true");
    maximize.appendChild(maxGlyph);
    actions.appendChild(maximize);
    var close = document.createElement("button");
    close.type = "button";
    close.className = "da-widget-icon-btn";
    close.setAttribute("data-da-close", "");
    close.setAttribute("aria-label", "Close");
    close.innerHTML = "&#10005;";
    actions.appendChild(close);

    brand.appendChild(titleBlock);
    hdrMain.appendChild(brand);
    hdrMain.appendChild(actions);

    var gradient = document.createElement("div");
    gradient.className = "da-widget-header-gradient";
    gradient.setAttribute("aria-hidden", "true");

    hdr.appendChild(hdrMain);
    hdr.appendChild(gradient);

    var body = document.createElement("div");
    body.className = "da-widget-body";
    var ifr = document.createElement("iframe");
    ifr.className = "da-widget-frame";
    ifr.title = titleSub;
    ifr.loading = "lazy";
    body.appendChild(ifr);

    var resizeEdges = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];
    resizeEdges.forEach(function (edge) {
      var handle = document.createElement("div");
      handle.className = "da-widget-resize-handle da-widget-resize-handle--" + edge;
      handle.setAttribute("data-da-resize", edge);
      handle.setAttribute("aria-hidden", "true");
      dlg.appendChild(handle);
    });

    dlg.appendChild(hdr);
    dlg.appendChild(body);
    el.appendChild(btn);
    el.appendChild(bd);
    el.appendChild(dlg);
    return el;
  }

  var root = buildRoot();
  var launcher = root.querySelector(".da-widget-launcher");
  var backdrop = root.querySelector("[data-da-backdrop]");
  var dialog = root.querySelector(".da-widget-dialog");
  var frame = root.querySelector(".da-widget-frame");
  var maximizeBtn = root.querySelector("[data-da-maximize]");
  var maxGlyphEl = maximizeBtn.querySelector(".da-widget-icon-glyph");
  var closeBtn = root.querySelector("[data-da-close]");
  var dragHandle = root.querySelector("[data-da-drag-handle]");
  var widgetTitleEl = root.querySelector("#da-widget-title");
  var widgetStrings = {};

  function wt(key) {
    return widgetStrings[key] || key;
  }

  function applyWidgetI18n() {
    var title = wt("widget.title");
    if (title && title !== "widget.title") {
      if (widgetTitleEl) widgetTitleEl.textContent = title;
      if (frame) frame.title = title;
    }
    closeBtn.setAttribute("aria-label", wt("widget.close"));
    if (maximized) {
      maximizeBtn.setAttribute("aria-label", wt("widget.restore"));
      maximizeBtn.setAttribute("title", wt("widget.restore"));
    } else {
      maximizeBtn.setAttribute("aria-label", wt("widget.maximize"));
      maximizeBtn.setAttribute("title", wt("widget.maximize"));
    }
  }

  function loadWidgetI18n(done) {
    var base = chatUrl.replace(/\/?$/, "/");
    fetch(base + "api/i18n", { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (data && data.strings && typeof data.strings === "object") {
          widgetStrings = data.strings;
        }
        applyWidgetI18n();
      })
      .catch(function () {
        /* keep defaults */
      })
      .finally(function () {
        if (done) done();
      });
  }

  if (placement === "header") {
    launcher.style.zIndex = "";
  } else {
    launcher.style.zIndex = String(zIndex);
  }
  backdrop.style.zIndex = String(zIndex + 1);
  dialog.style.zIndex = String(zIndex + 2);

  var drag = { active: false, startX: 0, startY: 0, startLeft: 0, startTop: 0 };
  var resizeState = {
    active: false,
    edge: "",
    startX: 0,
    startY: 0,
    startLeft: 0,
    startTop: 0,
    startWidth: 0,
    startHeight: 0,
  };
  var maximized = false;
  var savedLayout = null;
  var maximizeResizeObserver = null;
  var MAXIMIZE_PAD = 8;
  var ANCHOR_PAD = 16;
  var DIALOG_MIN_W = 360;
  var DIALOG_MIN_H = 320;
  var DIALOG_DEFAULT_W = 920;
  var DIALOG_DEFAULT_H = 720;

  function loadStyles() {
    var href = scriptBase() + "agent-widget.css";
    if (document.querySelector('link[data-da-widget-css="1"]')) return;
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.setAttribute("data-da-widget-css", "1");
    document.head.appendChild(link);
  }

  function mountLauncher() {
    if (!mountSelector) return;
    var slot = document.querySelector(mountSelector);
    if (!slot) return;
    slot.appendChild(launcher);
  }

  function isDefaultAnchoredDialog() {
    return dialog.getAttribute("data-da-default-anchor") === "1";
  }

  function setDefaultAnchored(isDefault) {
    if (isDefault) {
      dialog.setAttribute("data-da-default-anchor", "1");
    } else {
      dialog.removeAttribute("data-da-default-anchor");
    }
  }

  function getPlacementRect() {
    var container = getMaximizeContainerEl();
    if (!container) {
      return {
        left: 0,
        top: 0,
        width: window.innerWidth,
        height: window.innerHeight,
      };
    }
    var rect = container.getBoundingClientRect();
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
  }

  function getDefaultDialogSize(placement) {
    if (window.matchMedia("(max-width: 640px)").matches) {
      return {
        width: Math.max(DIALOG_MIN_W, window.innerWidth - ANCHOR_PAD * 2),
        height: Math.max(DIALOG_MIN_H, window.innerHeight - ANCHOR_PAD * 2),
      };
    }
    return {
      width: Math.min(
        DIALOG_DEFAULT_W,
        Math.max(DIALOG_MIN_W, placement.width - ANCHOR_PAD * 2)
      ),
      height: Math.min(
        DIALOG_DEFAULT_H,
        Math.max(DIALOG_MIN_H, placement.height - ANCHOR_PAD * 2)
      ),
    };
  }

  function clampDialogBox(left, top, width, height) {
    var place = getPlacementRect();
    var maxW = Math.max(DIALOG_MIN_W, place.width - ANCHOR_PAD * 2);
    var maxH = Math.max(DIALOG_MIN_H, place.height - ANCHOR_PAD * 2);
    width = Math.min(Math.max(DIALOG_MIN_W, width), maxW);
    height = Math.min(Math.max(DIALOG_MIN_H, height), maxH);
    var minLeft = place.left + ANCHOR_PAD;
    var minTop = place.top + ANCHOR_PAD;
    var maxLeft = place.left + place.width - width - ANCHOR_PAD;
    var maxTop = place.top + place.height - height - ANCHOR_PAD;
    left = Math.min(Math.max(left, minLeft), Math.max(minLeft, maxLeft));
    top = Math.min(Math.max(top, minTop), Math.max(minTop, maxTop));
    return { left: left, top: top, width: width, height: height };
  }

  function applyDialogBox(box) {
    setDefaultAnchored(false);
    dialog.classList.add("da-widget-dialog--placed");
    dialog.style.left = box.left + "px";
    dialog.style.top = box.top + "px";
    dialog.style.width = box.width + "px";
    dialog.style.height = box.height + "px";
    dialog.style.transform = "none";
  }

  function getAnchorBounds() {
    var place = getPlacementRect();
    var size = getDefaultDialogSize(place);
    return clampDialogBox(
      place.left + place.width - size.width - ANCHOR_PAD,
      place.top + place.height - size.height - ANCHOR_PAD,
      size.width,
      size.height
    );
  }

  function anchorDialogDefault() {
    var box = getAnchorBounds();
    applyDialogBox(box);
    setDefaultAnchored(true);
  }

  function captureLayout() {
    if (isDefaultAnchoredDialog()) {
      return { defaultAnchor: true };
    }
    var rect = dialog.getBoundingClientRect();
    return {
      centered: false,
      left: rect.left + "px",
      top: rect.top + "px",
      width: rect.width + "px",
      height: rect.height + "px",
    };
  }

  function applyLayout(layout) {
    setDefaultAnchored(false);
    dialog.classList.add("da-widget-dialog--placed");
    dialog.style.left = layout.left;
    dialog.style.top = layout.top;
    dialog.style.width = layout.width;
    dialog.style.height = layout.height;
    dialog.style.transform = "none";
  }

  function setMaximizeUi(isMax) {
    maximized = isMax;
    dialog.classList.toggle("da-widget-dialog--maximized", isMax);
    root.classList.toggle("da-widget-maximized", isMax);
    maximizeBtn.setAttribute("aria-label", isMax ? wt("widget.restore") : wt("widget.maximize"));
    maximizeBtn.setAttribute("title", isMax ? wt("widget.restore") : wt("widget.maximize"));
    maxGlyphEl.className =
      "da-widget-icon-glyph " +
      (isMax
        ? "da-widget-icon-glyph--restore"
        : "da-widget-icon-glyph--maximize");
  }

  function getMaximizeContainerEl() {
    if (!maximizeContainerSelector) return null;
    return document.querySelector(maximizeContainerSelector);
  }

  function getMaximizeBounds() {
    var container = getMaximizeContainerEl();
    if (!container) {
      return {
        backdrop: { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight },
        dialog: {
          left: MAXIMIZE_PAD,
          top: MAXIMIZE_PAD,
          width: window.innerWidth - MAXIMIZE_PAD * 2,
          height: window.innerHeight - MAXIMIZE_PAD * 2,
        },
      };
    }
    var rect = container.getBoundingClientRect();
    return {
      backdrop: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      dialog: {
        left: rect.left + MAXIMIZE_PAD,
        top: rect.top + MAXIMIZE_PAD,
        width: Math.max(0, rect.width - MAXIMIZE_PAD * 2),
        height: Math.max(0, rect.height - MAXIMIZE_PAD * 2),
      },
    };
  }

  function applyBackdropBounds(rect) {
    backdrop.style.inset = "auto";
    backdrop.style.left = rect.left + "px";
    backdrop.style.top = rect.top + "px";
    backdrop.style.width = rect.width + "px";
    backdrop.style.height = rect.height + "px";
  }

  function clearBackdropBounds() {
    backdrop.style.inset = "";
    backdrop.style.left = "";
    backdrop.style.top = "";
    backdrop.style.width = "";
    backdrop.style.height = "";
  }

  function applyMaximizeBounds() {
    var bounds = getMaximizeBounds();
    applyBackdropBounds(bounds.backdrop);
    setDefaultAnchored(false);
    dialog.classList.add("da-widget-dialog--placed");
    dialog.style.left = bounds.dialog.left + "px";
    dialog.style.top = bounds.dialog.top + "px";
    dialog.style.width = bounds.dialog.width + "px";
    dialog.style.height = bounds.dialog.height + "px";
    dialog.style.transform = "none";
  }

  function syncMaximizeBounds() {
    if (maximized) applyMaximizeBounds();
  }

  function watchMaximizeContainer() {
    unwatchMaximizeContainer();
    var el = getMaximizeContainerEl();
    if (!el || typeof ResizeObserver === "undefined") return;
    maximizeResizeObserver = new ResizeObserver(syncMaximizeBounds);
    maximizeResizeObserver.observe(el);
  }

  function unwatchMaximizeContainer() {
    if (maximizeResizeObserver) {
      maximizeResizeObserver.disconnect();
      maximizeResizeObserver = null;
    }
  }

  function startMaximizeTracking() {
    window.addEventListener("resize", syncMaximizeBounds);
    window.addEventListener("scroll", syncMaximizeBounds, true);
    watchMaximizeContainer();
  }

  function stopMaximizeTracking() {
    window.removeEventListener("resize", syncMaximizeBounds);
    window.removeEventListener("scroll", syncMaximizeBounds, true);
    unwatchMaximizeContainer();
    clearBackdropBounds();
  }

  function maximizeDialog() {
    if (maximized || window.matchMedia("(max-width: 640px)").matches) return;
    savedLayout = captureLayout();
    drag.active = false;
    setMaximizeUi(true);
    applyMaximizeBounds();
    startMaximizeTracking();
  }

  function restoreDialog() {
    if (!maximized) return;
    stopMaximizeTracking();
    setMaximizeUi(false);
    if (savedLayout && savedLayout.defaultAnchor) {
      anchorDialogDefault();
      savedLayout = null;
    } else if (savedLayout) {
      applyLayout(savedLayout);
      savedLayout = null;
    } else {
      anchorDialogDefault();
    }
  }

  function toggleMaximize() {
    if (maximized) {
      restoreDialog();
    } else {
      maximizeDialog();
    }
  }

  function notifyIframeOpen() {
    if (!frame.contentWindow) return;
    try {
      frame.contentWindow.postMessage({ type: "dia-agent-open" }, "*");
    } catch (_e) {
      /* cross-origin or not loaded yet */
    }
  }

  function openDialog() {
    if (!frame.src) {
      frame.src = chatUrl;
      frame.addEventListener("load", function onFirstLoad() {
        frame.removeEventListener("load", onFirstLoad);
        notifyIframeOpen();
      });
    } else {
      notifyIframeOpen();
    }
    root.classList.add("da-widget-open");
    launcher.setAttribute("aria-expanded", "true");
    backdrop.hidden = false;
    dialog.hidden = false;
    anchorDialogDefault();
    closeBtn.focus();
  }

  function closeDialog() {
    if (maximized) {
      stopMaximizeTracking();
      setMaximizeUi(false);
      savedLayout = null;
    }
    root.classList.remove("da-widget-open");
    launcher.setAttribute("aria-expanded", "false");
    backdrop.hidden = true;
    dialog.hidden = true;
    drag.active = false;
    anchorDialogDefault();
    launcher.focus();
  }

  function pinDialogPosition() {
    setDefaultAnchored(false);
    var rect = dialog.getBoundingClientRect();
    dialog.classList.add("da-widget-dialog--placed");
    dialog.style.width = rect.width + "px";
    dialog.style.height = rect.height + "px";
    dialog.style.left = rect.left + "px";
    dialog.style.top = rect.top + "px";
    dialog.style.transform = "none";
    return rect;
  }

  function onResizeStart(edge, clientX, clientY) {
    if (maximized || window.matchMedia("(max-width: 640px)").matches) return;
    dialog.style.transition = "none";
    var rect = pinDialogPosition();
    resizeState.active = true;
    resizeState.edge = edge;
    resizeState.startX = clientX;
    resizeState.startY = clientY;
    resizeState.startLeft = rect.left;
    resizeState.startTop = rect.top;
    resizeState.startWidth = rect.width;
    resizeState.startHeight = rect.height;
  }

  function onResizeMove(clientX, clientY) {
    if (!resizeState.active) return;
    var dx = clientX - resizeState.startX;
    var dy = clientY - resizeState.startY;
    var edge = resizeState.edge;
    var left = resizeState.startLeft;
    var top = resizeState.startTop;
    var width = resizeState.startWidth;
    var height = resizeState.startHeight;

    if (edge.indexOf("e") !== -1) {
      width = resizeState.startWidth + dx;
    }
    if (edge.indexOf("w") !== -1) {
      width = resizeState.startWidth - dx;
      left = resizeState.startLeft + resizeState.startWidth - width;
    }
    if (edge.indexOf("s") !== -1) {
      height = resizeState.startHeight + dy;
    }
    if (edge.indexOf("n") !== -1) {
      height = resizeState.startHeight - dy;
      top = resizeState.startTop + resizeState.startHeight - height;
    }

    var box = clampDialogBox(left, top, width, height);
    applyDialogBox(box);
  }

  function onResizeEnd() {
    if (!resizeState.active) return;
    resizeState.active = false;
    resizeState.edge = "";
    dialog.style.transition = "";
  }

  function onDragStart(clientX, clientY) {
    if (maximized || window.matchMedia("(max-width: 640px)").matches) return;
    dialog.style.transition = "none";
    var rect = pinDialogPosition();
    drag.active = true;
    drag.startX = clientX;
    drag.startY = clientY;
    drag.startLeft = rect.left;
    drag.startTop = rect.top;
  }

  function onDragMove(clientX, clientY) {
    if (!drag.active) return;
    var dx = clientX - drag.startX;
    var dy = clientY - drag.startY;
    var rect = dialog.getBoundingClientRect();
    var box = clampDialogBox(
      drag.startLeft + dx,
      drag.startTop + dy,
      rect.width,
      rect.height
    );
    dialog.style.left = box.left + "px";
    dialog.style.top = box.top + "px";
  }

  function onDragEnd() {
    drag.active = false;
    dialog.style.transition = "";
  }

  launcher.addEventListener("click", openDialog);
  maximizeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    toggleMaximize();
  });
  closeBtn.addEventListener("click", closeDialog);

  if (closeOnBackdrop) {
    backdrop.addEventListener("click", closeDialog);
  }

  dragHandle.addEventListener("mousedown", function (e) {
    if (
      e.button !== 0 ||
      e.target.closest("[data-da-close]") ||
      e.target.closest("[data-da-maximize]") ||
      e.target.closest("[data-da-resize]")
    ) {
      return;
    }
    e.preventDefault();
    onDragStart(e.clientX, e.clientY);
  });

  dialog.querySelectorAll("[data-da-resize]").forEach(function (handle) {
    handle.addEventListener("mousedown", function (e) {
      if (e.button !== 0 || maximized) return;
      e.preventDefault();
      e.stopPropagation();
      onResizeStart(handle.getAttribute("data-da-resize"), e.clientX, e.clientY);
    });
  });

  document.addEventListener("mousemove", function (e) {
    onResizeMove(e.clientX, e.clientY);
    onDragMove(e.clientX, e.clientY);
  });
  document.addEventListener("mouseup", function () {
    onResizeEnd();
    onDragEnd();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && root.classList.contains("da-widget-open")) {
      e.preventDefault();
      closeDialog();
    }
  });

  loadStyles();
  window.addEventListener("message", function (event) {
    if (!frame.contentWindow || event.source !== frame.contentWindow) return;
    var data = event.data;
    if (!data || typeof data.type !== "string") return;
    if (data.type === "dia-agent-open-trade" && window.parent && window.parent !== window) {
      window.parent.postMessage(data, "*");
      closeDialog();
    }
    if (data.type === "dia-agent-close") {
      closeDialog();
    }
  });
  loadWidgetI18n(function () {
    document.body.appendChild(root);
    mountLauncher();
  });
})();
