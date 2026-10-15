/*
 * Cashea support widget loader — the only thing a host page includes:
 *
 *   <script src="https://<chat-host>/widget.js"></script>
 *   <script>
 *     casheaChat.init({
 *       // Optional. Return the signed-in user's Firebase ID token (or null),
 *       // and the chat acts as that user. Omit it for an anonymous chat.
 *       getToken: function () { return auth.currentUser?.getIdToken() ?? null; },
 *       // Optional. The user tapped an order card: show that order (by uuid).
 *       onOpenOrder: function (orderUuid) { router.navigate("/orders/" + orderUuid); },
 *       // Optional. A one-time nudge next to the launcher, once per browser.
 *       greeting: "¿Te ayudo con tus órdenes?",
 *     });
 *     // On sign-out, so the next user never inherits this one's chat:
 *     casheaChat.destroy();
 *   </script>
 *
 * Injects the launcher — Cheo, the Cashea orb — and, on first open,
 * an iframe to <chat-host>/embed that holds the whole chat UI. Plain JS (no
 * build step) with inline styles so it runs on any host; the few keyframes
 * live in one injected <style>, scoped to the launcher's id.
 *
 * Token handshake (see frontend/src/lib/host/host-identity.ts): the iframe
 * posts {type: "cashea-chat:token-request", id}; this loader calls getToken()
 * and answers {type: "cashea-chat:token", id, token} to the chat origin only.
 * Requests are honored only from this loader's own iframe at that origin.
 * The same goes for {type: "cashea-chat:open-order", orderUuid} (only a UUID
 * is passed on — the host decides where that leads) and
 * {type: "cashea-chat:close"} (Esc inside the chat).
 */
(function () {
  "use strict";

  if (window.casheaChat) return;

  // Where this script was served from — the chat app's origin, unless the host
  // overrides it with init({ baseUrl }).
  var script = document.currentScript;
  var scriptOrigin = script && script.src ? new URL(script.src).origin : "";

  var TOKEN_REQUEST = "cashea-chat:token-request";
  var TOKEN_RESPONSE = "cashea-chat:token";
  var OPEN_ORDER = "cashea-chat:open-order";
  var CLOSE = "cashea-chat:close";
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  var GREETED_KEY = "cashea-chat:greeted";
  var EASE = "cubic-bezier(0.16, 1, 0.3, 1)";
  var SPRING = "cubic-bezier(0.34, 1.56, 0.64, 1)";

  // Cheo, the orb: the <cheo-orb> custom element from @cashea/cheo, loaded
  // from <chat-host>/cheo-orb.js (a copy of the package's dist/cheo-orb.js,
  // see frontend/vendor/README.md). It follows the pointer and draws its own
  // blink; this file only adds the aura around it while the chat is closed.
  var ORB_SIZE = 56;
  var CHEO = '<cheo-orb size="' + ORB_SIZE + '" follow></cheo-orb>';

  // Scoped by id so nothing leaks into the host page. The aura is a yellow
  // glow behind the orb that breathes while the chat is closed, so the
  // launcher catches the eye; it stops under reduced motion.
  var STYLE =
    "#cashea-chat-launcher{display:flex;align-items:center;justify-content:center}" +
    "#cashea-chat-launcher cheo-orb:not(:defined){display:inline-block;width:" + ORB_SIZE + "px;height:" + ORB_SIZE + "px}" +
    "#cashea-chat-launcher cheo-orb{position:relative}" +
    "#cashea-chat-launcher::before{content:'';position:absolute;left:50%;top:50%;width:112px;height:112px;margin:-56px 0 0 -56px;border-radius:50%;pointer-events:none;" +
    "background:radial-gradient(circle,rgba(253,250,61,.8) 0,rgba(253,250,61,.5) 36%,rgba(253,250,61,0) 70%);" +
    "opacity:0;transform:scale(.7);transition:opacity 240ms " + EASE + ",transform 240ms " + EASE + "}" +
    "#cashea-chat-launcher[aria-expanded=false]::before{opacity:1;transform:none;animation:cc-aura 2.6s ease-in-out infinite alternate}" +
    "@keyframes cc-aura{from{opacity:.65;transform:scale(.92)}to{opacity:1;transform:scale(1.08)}}" +
    "#cashea-chat-launcher.cc-squash cheo-orb{animation:cc-squash 320ms " + SPRING + "}" +
    "@keyframes cc-squash{35%{transform:scale(1.14,.86)}70%{transform:scale(.96,1.04)}}" +
    "@media (prefers-reduced-motion:reduce){#cashea-chat-launcher *,#cashea-chat-launcher::before{animation:none!important;transition:none!important}}";

  // Registers <cheo-orb> once. Until the script arrives the launcher shows an
  // empty, same-sized slot; if it never does the launcher still opens the chat.
  function loadOrb(baseUrl) {
    if (window.customElements && window.customElements.get("cheo-orb")) return;
    var orbScript = document.createElement("script");
    orbScript.src = baseUrl + "/cheo-orb.js";
    orbScript.async = true;
    orbScript.onerror = function () {
      console.error("[casheaChat] Could not load " + orbScript.src);
    };
    document.head.appendChild(orbScript);
  }

  // Luz tokens (merchant-web): gray-1000, gray-200, shadow-xl.
  var INK = "#181919";
  var BORDER = "#E6E7E8";
  var reducedMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };
  var SHADOW = "0px 12px 40px 0px rgba(121, 125, 134, 0.2)";
  var Z = "2147483000";

  // The one live widget, or null. Kept here so destroy() can find it.
  var current = null;

  function css(el, styles) {
    for (var k in styles) el.style[k] = styles[k];
  }

  function init(options) {
    options = options || {};
    if (current) return;

    var baseUrl = (options.baseUrl || scriptOrigin).replace(/\/$/, "");
    if (!baseUrl) {
      console.error("[casheaChat] Could not resolve the chat URL — pass init({ baseUrl }).");
      return;
    }
    var chatOrigin = new URL(baseUrl).origin;
    var getToken = typeof options.getToken === "function" ? options.getToken : null;
    var onOpenOrder = typeof options.onOpenOrder === "function" ? options.onOpenOrder : null;
    var greetingText = typeof options.greeting === "string" ? options.greeting : "";

    var open = false;
    var panel = null;
    var frame = null;

    var launcher = document.createElement("button");
    launcher.id = "cashea-chat-launcher";
    launcher.type = "button";
    launcher.setAttribute("aria-label", "Abrir chat de soporte");
    launcher.setAttribute("aria-expanded", "false");
    launcher.innerHTML = CHEO;
    css(launcher, {
      position: "fixed",
      right: "20px",
      bottom: "16px",
      width: "76px",
      height: "68px",
      border: "none",
      background: "none",
      cursor: "pointer",
      display: "flex",
      padding: "0",
      zIndex: Z,
      transition: "transform 200ms " + SPRING,
      WebkitTapHighlightColor: "transparent",
    });
    var orb = launcher.querySelector("cheo-orb");
    loadOrb(baseUrl);

    var style = document.createElement("style");
    style.id = "cashea-chat-style";
    style.textContent = STYLE;
    document.head.appendChild(style);

    // Hover lifts Cheo a little and wakes its eyes (the orb follows the pointer
    // on its own).
    launcher.addEventListener("mouseenter", function () {
      launcher.style.transform = "translateY(-2px) scale(1.04)";
      orb.awake = true;
    });
    launcher.addEventListener("mouseleave", function () {
      launcher.style.transform = "";
      orb.awake = false;
    });

    // Built on first open, so a host page that never opens the chat never
    // loads the chat app.
    function buildPanel() {
      var src = new URL(baseUrl + "/embed");
      if (getToken) {
        // Tells the iframe which parent to trust and that it may ask for a token.
        src.searchParams.set("host", window.location.origin);
        src.searchParams.set("auth", "1");
      }
      frame = document.createElement("iframe");
      frame.src = src.toString();
      frame.title = "Chat de soporte Cashea";
      css(frame, { width: "100%", height: "100%", border: "0", display: "block" });

      var el = document.createElement("div");
      el.id = "cashea-chat-panel";
      css(el, {
        position: "fixed",
        right: "24px",
        bottom: "92px",
        width: "400px",
        height: "640px",
        maxWidth: "calc(100vw - 32px)",
        maxHeight: "calc(100vh - 116px)",
        borderRadius: "16px",
        border: "1px solid " + BORDER,
        overflow: "hidden",
        background: "#FFFFFF",
        boxShadow: SHADOW,
        zIndex: Z,
        // Starts hidden, tucked into Cheo; setOpen() grows it out of the
        // cloud (the origin sits on the launcher, below the panel).
        opacity: "0",
        transform: closedTransform(),
        transformOrigin: "calc(100% - 38px) calc(100% + 42px)",
        visibility: "hidden",
      });
      el.appendChild(frame);
      document.body.appendChild(el);
      return el;
    }

    function answer(id, token) {
      if (!frame || !frame.contentWindow) return;
      frame.contentWindow.postMessage(
        { type: TOKEN_RESPONSE, id: id, token: typeof token === "string" ? token : null },
        chatOrigin
      );
    }

    function onMessage(event) {
      if (!frame || event.source !== frame.contentWindow) return;
      if (event.origin !== chatOrigin) return;
      var data = event.data || {};
      if (data.type === CLOSE) {
        setOpen(false);
        launcher.focus();
        return;
      }
      if (data.type === OPEN_ORDER) {
        if (onOpenOrder && typeof data.orderUuid === "string" && UUID.test(data.orderUuid)) {
          onOpenOrder(data.orderUuid);
        }
        return;
      }
      if (!getToken || data.type !== TOKEN_REQUEST || typeof data.id !== "string") return;
      Promise.resolve()
        .then(getToken)
        .then(
          function (token) {
            answer(data.id, token);
          },
          function (err) {
            console.error("[casheaChat] getToken failed", err);
            answer(data.id, null);
          }
        );
    }

    // Reduced motion keeps only a fade: no growing out of the cloud.
    function closedTransform() {
      return reducedMotion.matches ? "none" : "scale(0.2)";
    }

    function setOpen(next) {
      if (next === open) return;
      open = next;
      if (open && !panel) {
        panel = buildPanel();
        // Commit the hidden state before animating to the open one.
        void panel.offsetHeight;
      }
      if (panel) {
        css(panel, open
          ? {
              opacity: "1",
              transform: "scale(1)",
              visibility: "visible",
              transition:
                "opacity 180ms " + EASE + ", transform 360ms " + SPRING + ", visibility 0s",
            }
          : {
              opacity: "0",
              transform: closedTransform(),
              visibility: "hidden",
              transition:
                "opacity 160ms ease-in, transform 180ms ease-in, visibility 0s linear 180ms",
            });
      }
      // Open: Cheo smiles ^^ (and stays the button that closes the chat).
      orb.mood = open ? "happy" : "idle";
      launcher.classList.remove("cc-squash");
      void launcher.offsetWidth;
      launcher.classList.add("cc-squash");
      launcher.setAttribute("aria-expanded", String(open));
      launcher.setAttribute("aria-label", open ? "Cerrar chat de soporte" : "Abrir chat de soporte");
      if (open) hideGreeting();
    }

    function onClick() {
      setOpen(!open);
    }

    function onKeyDown(event) {
      if (event.key === "Escape" && open) setOpen(false);
    }

    // A one-time nudge beside the launcher. localStorage can throw (private
    // mode, blocked storage): then it simply shows, which is harmless.
    var greeting = null;
    var greetingTimer = null;
    function seenGreeting() {
      try {
        return window.localStorage.getItem(GREETED_KEY) === "1";
      } catch {
        return false;
      }
    }
    function hideGreeting() {
      if (greetingTimer) clearTimeout(greetingTimer);
      // Opening the chat counts as having been greeted, shown or not.
      try {
        window.localStorage.setItem(GREETED_KEY, "1");
      } catch {
        /* ignore */
      }
      if (!greeting) return;
      greeting.remove();
      greeting = null;
    }
    function showGreeting() {
      greeting = document.createElement("button");
      greeting.type = "button";
      greeting.textContent = greetingText;
      css(greeting, {
        position: "fixed",
        right: "104px",
        bottom: "34px",
        maxWidth: "240px",
        padding: "10px 14px",
        borderRadius: "16px 16px 4px 16px",
        border: "1px solid " + BORDER,
        background: "#FFFFFF",
        color: INK,
        font: "500 14px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif",
        textAlign: "left",
        boxShadow: SHADOW,
        cursor: "pointer",
        zIndex: Z,
      });
      greeting.addEventListener("click", function () {
        setOpen(true);
      });
      document.body.appendChild(greeting);
      if (greeting.animate) {
        greeting.animate(
          [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }],
          { duration: 250, easing: EASE }
        );
      }
    }
    if (greetingText && !seenGreeting()) {
      greetingTimer = setTimeout(showGreeting, 1500);
    }

    launcher.addEventListener("click", onClick);
    window.addEventListener("message", onMessage);
    document.addEventListener("keydown", onKeyDown);
    document.body.appendChild(launcher);

    current = {
      teardown: function () {
        window.removeEventListener("message", onMessage);
        document.removeEventListener("keydown", onKeyDown);
        if (greetingTimer) clearTimeout(greetingTimer);
        if (greeting) greeting.remove();
        launcher.remove();
        style.remove();
        if (panel) panel.remove();
      },
    };
  }

  /** Removes the widget and its session. Call on sign-out; init() again after. */
  function destroy() {
    if (!current) return;
    current.teardown();
    current = null;
  }

  window.casheaChat = { init: init, destroy: destroy };
})();
