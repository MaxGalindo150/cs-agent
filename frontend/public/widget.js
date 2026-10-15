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
 * Injects a launcher bubble and, on first open, an iframe to <chat-host>/embed
 * that holds the whole chat UI. Plain JS (no build step) with inline styles so
 * it runs on any host and the host's CSS can't restyle it.
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

  var ICON_CHAT =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/></svg>';
  var ICON_CLOSE =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

  // Luz tokens (merchant-web): yellow-cashea-500, gray-1000, gray-200, shadow-xl.
  var YELLOW = "#FDFA3D";
  var INK = "#181919";
  var BORDER = "#E6E7E8";
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
    launcher.innerHTML = ICON_CHAT;
    css(launcher, {
      position: "fixed",
      right: "24px",
      bottom: "24px",
      width: "56px",
      height: "56px",
      borderRadius: "9999px",
      border: "none",
      background: YELLOW,
      color: INK,
      boxShadow: SHADOW,
      cursor: "pointer",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "0",
      zIndex: Z,
      transition: "transform 200ms " + EASE + ", box-shadow 200ms " + EASE,
    });
    launcher.addEventListener("mouseenter", function () {
      launcher.style.transform = "scale(1.06)";
    });
    launcher.addEventListener("mouseleave", function () {
      launcher.style.transform = "scale(1)";
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
        bottom: "96px",
        width: "400px",
        height: "640px",
        maxWidth: "calc(100vw - 32px)",
        maxHeight: "calc(100vh - 120px)",
        borderRadius: "16px",
        border: "1px solid " + BORDER,
        overflow: "hidden",
        background: "#FFFFFF",
        boxShadow: SHADOW,
        zIndex: Z,
        // Starts hidden; setOpen() animates it in.
        opacity: "0",
        transform: "translateY(12px) scale(0.98)",
        transformOrigin: "bottom right",
        visibility: "hidden",
        transition:
          "opacity 200ms " + EASE + ", transform 200ms " + EASE + ", visibility 0s linear 200ms",
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
              transform: "translateY(0) scale(1)",
              visibility: "visible",
              transition:
                "opacity 200ms " + EASE + ", transform 200ms " + EASE + ", visibility 0s",
            }
          : {
              opacity: "0",
              transform: "translateY(12px) scale(0.98)",
              visibility: "hidden",
              transition:
                "opacity 150ms ease-in, transform 150ms ease-in, visibility 0s linear 150ms",
            });
      }
      launcher.innerHTML = open ? ICON_CLOSE : ICON_CHAT;
      var icon = launcher.firstChild;
      if (icon && icon.animate) {
        icon.animate(
          [{ transform: "rotate(-90deg) scale(0.6)", opacity: 0 }, { transform: "none", opacity: 1 }],
          { duration: 200, easing: EASE }
        );
      }
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
        right: "92px",
        bottom: "32px",
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
