"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var src_exports = {};
__export(src_exports, {
  CHEO_COSTUMES: () => CHEO_COSTUMES,
  CHEO_MOODS: () => CHEO_MOODS,
  CHEO_THEMES: () => CHEO_THEMES,
  CheoOrbElement: () => CheoOrbElement,
  DEFAULT_TAG_NAME: () => DEFAULT_TAG_NAME,
  defineCheoOrb: () => defineCheoOrb,
  gazeOffset: () => gazeOffset
});
module.exports = __toCommonJS(src_exports);

// src/styles.ts
var LIGHT = "--_body:var(--cheo-body,#FEFEFE);--_ink:var(--cheo-ink,#0A0A0A);--_accent:var(--cheo-accent,#FDFA3D);--_bg:var(--cheo-bg,#FEFEFE)";
var DARK = "--_body:var(--cheo-body,#FEFEFE);--_ink:var(--cheo-ink,#0A0A0A);--_accent:var(--cheo-accent,#FDFC8A);--_bg:var(--cheo-bg,#0A0A0A)";
var COSTUME = "--_red:var(--cheo-red,#E23D3D);--_orange:var(--cheo-orange,#FF8A3D);--_green:var(--cheo-green,#3FA34D)";
var GLANCE_PROPERTY = "--_cheo-glance-x";
var LEAN = "rotate(-22deg)";
var EYE_TRANSFORM = `translate(calc(var(--_gaze-x,0px) + var(${GLANCE_PROPERTY},0px)),var(--_gaze-y,0px)) ${LEAN}`;
var BROW_TRANSFORM = `translate(calc(var(--_gaze-x,0px)*.5),calc(var(--_gaze-y,0px)*.5))`;
var STYLES = `
:host{${LIGHT};${COSTUME};position:relative;display:inline-flex;flex-shrink:0}
:host([theme=dark]){${DARK}}
@media (prefers-color-scheme:dark){:host([theme=auto]){${DARK}}}
:host([hidden]){display:none}
.face{--_gaze-x:0px;--_gaze-y:0px;--_line:max(1px,calc(var(--_size)*.036));position:relative;display:flex;flex-shrink:0;align-items:center;justify-content:center;width:var(--_size);height:var(--_size)}
.orb{position:relative;display:block;box-sizing:border-box;width:100%;height:100%;border:var(--_line) solid var(--_ink);border-radius:42% 58% 55% 45%/48% 52% 48% 52%;
background:linear-gradient(145deg,var(--_body) 0%,var(--_body) 55%,color-mix(in srgb,var(--_body) 70%,var(--_accent)) 100%);background-size:180% 180%;
box-shadow:0 calc(2px*var(--_k)) calc(10px*var(--_k)) color-mix(in srgb,var(--_accent) 60%,transparent),inset calc(-2px*var(--_k)) calc(-3px*var(--_k)) calc(6px*var(--_k)) color-mix(in srgb,var(--_ink) 12%,transparent)}
.ring{position:absolute;inset:0;display:none;border-radius:999px;background:color-mix(in srgb,var(--_accent) 70%,transparent)}
[data-live] .ring{display:block}
.eye{position:absolute;top:36%;width:var(--_eye-w);height:var(--_eye-h);border-radius:999px;background:var(--_ink);transform:${EYE_TRANSFORM};will-change:transform}
.l{left:31%}.r{right:31%}
[data-mood=listening] .eye{top:41%;height:calc(var(--_eye-h)*1.15)}
[data-mood=thinking] .eye{top:32%}
.brow{position:absolute;top:23%;display:none;width:15%;height:9%;box-sizing:border-box;border:0 solid var(--_ink);border-top-width:var(--_line);border-radius:999px 999px 0 0;transform:${BROW_TRANSFORM} ${LEAN}}
[data-brows] .brow{display:block}
.bl{left:27%}.br{right:27%;top:20%}
[data-mood=listening] .brow,[data-mood=idle][data-awake] .brow{top:19%}[data-mood=listening] .br,[data-mood=idle][data-awake] .br{top:15%}
@media (hover:hover){:host(:hover) [data-mood=idle] .brow{top:19%}:host(:hover) [data-mood=idle] .br{top:15%}}
[data-mood=thinking] .bl{top:19%;transform:${BROW_TRANSFORM} rotate(-34deg)}[data-mood=thinking] .br{top:16%;transform:${BROW_TRANSFORM} rotate(-8deg)}
[data-mood=happy] .brow{top:20%}
[data-mood=idle][data-awake] .eye{height:calc(var(--_eye-h)*1.2)}
@media (hover:hover){:host(:hover) [data-mood=idle] .eye{height:calc(var(--_eye-h)*1.2)}}
.mouth{position:absolute;left:50%;top:53%;display:none;width:40%;height:19%;box-sizing:border-box;border:0 solid var(--_ink);border-bottom-width:calc(var(--_line)*1.1);border-radius:8% 8% 70% 70%/10% 10% 100% 100%;transform:translateX(-50%) rotate(-6deg);transform-origin:50% 0}
.cheek{position:absolute;left:28%;top:55%;display:none;width:4%;height:9%;border-left:var(--_line) solid var(--_ink);border-radius:999px;transform:rotate(28deg)}
[data-mood=happy] .mouth,[data-mood=happy] .cheek{display:block}
.dot{position:absolute;top:calc(-2px*var(--_d));right:calc(-2px*var(--_d));display:none;width:calc(8px*var(--_d));height:calc(8px*var(--_d));border-radius:999px;background:var(--_accent);box-shadow:0 0 0 calc(1px*var(--_d)) var(--_ink),0 0 0 calc(2.5px*var(--_d)) var(--_bg)}
[data-ready] .dot{display:block}
.hat,.hat::before,.hat::after,.stache,.stache::before,.stache::after{position:absolute;box-sizing:border-box;border:var(--_line) solid var(--_ink)}
.hat,.stache,.heart{display:none}
.hat::before,.hat::after,.stache::before,.stache::after{content:''}
[data-costume] .hat,[data-costume=mariachi] .stache,[data-heart] .heart{display:block}
[data-costume=spooky] .hat{left:13%;top:-20%;width:74%;height:40%;border-radius:50% 50% 46% 46%/72% 72% 36% 36%;background:var(--_orange)}
[data-costume=spooky] .hat::before{left:32%;top:4%;width:36%;height:88%;border-width:0 var(--_line);border-radius:50%}
[data-costume=spooky] .hat::after{left:45%;top:-26%;width:13%;height:34%;border-radius:40% 40% 20% 20%;background:var(--_green);transform:rotate(10deg)}
[data-costume=santa] .hat{left:17%;top:-30%;width:60%;height:50%;border-radius:70% 30% 6% 6%/100% 100% 0 0;background:var(--_red);transform:rotate(-12deg);transform-origin:50% 100%}
[data-costume=santa] .hat::before{left:-9%;bottom:-11%;width:118%;height:26%;border-radius:999px;background:var(--_body)}
[data-costume=santa] .hat::after{left:62%;top:-16%;width:30%;aspect-ratio:1;border-radius:999px;background:var(--_body)}
[data-costume=mariachi] .hat{left:-22%;top:-14%;width:144%;height:30%;border-radius:50%;background:var(--_accent)}
[data-costume=mariachi] .hat::before{left:30%;top:-72%;width:40%;height:118%;border-radius:46% 46% 14% 14%/60% 60% 12% 12%;background:var(--_accent)}
[data-costume=mariachi] .hat::after{left:29%;top:8%;width:42%;height:22%;border-radius:50%;background:var(--_ink)}
[data-costume=mariachi] .stache{left:50%;top:55%;width:40%;height:7%;border-radius:999px;background:var(--_ink);transform:translateX(-50%)}
[data-costume=mariachi] .stache::before,[data-costume=mariachi] .stache::after{top:-70%;width:18%;height:120%;border-radius:999px;background:var(--_ink)}
[data-costume=mariachi] .stache::before{left:-6%;transform:rotate(-20deg)}[data-costume=mariachi] .stache::after{right:-6%;transform:rotate(20deg)}
[data-costume=mariachi] .mouth,[data-costume=mariachi] .cheek{display:none}
.heart{position:absolute;left:58%;top:30%;width:34%;height:auto;overflow:visible;fill:var(--_accent);stroke:var(--_ink);stroke-width:2;stroke-linejoin:round;transform:translate(12%,-24%);transform-origin:50% 50%}
@keyframes cheo-morph{0%,100%{border-radius:42% 58% 55% 45%/48% 52% 48% 52%}33%{border-radius:58% 42% 48% 52%/52% 48% 56% 44%}66%{border-radius:48% 52% 42% 58%/44% 56% 48% 52%}}
@keyframes cheo-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
@keyframes cheo-drift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}
@keyframes cheo-ring{0%{transform:scale(1);opacity:.6}100%{transform:scale(2);opacity:0}}
@keyframes cheo-blink{0%,42%,48%,100%{transform:${EYE_TRANSFORM} scaleY(1)}45%{transform:${EYE_TRANSFORM} scaleY(.12)}}
@keyframes cheo-glance{0%,60%,100%{${GLANCE_PROPERTY}:0px}70%,82%{${GLANCE_PROPERTY}:var(--_reach)}88%,96%{${GLANCE_PROPERTY}:calc(var(--_reach)*-.6)}}
@keyframes cheo-think{0%,100%{transform:translate(calc(var(--_reach)*-.8),calc(var(--_reach)*-.9)) ${LEAN} scaleY(.55)}50%{transform:translate(calc(var(--_reach)*.8),calc(var(--_reach)*-.9)) ${LEAN} scaleY(.55)}}
@keyframes cheo-smile{0%{transform:translateX(-50%) rotate(-6deg) scale(.3);opacity:0}25%,100%{transform:translateX(-50%) rotate(-6deg) scale(1);opacity:1}}
@keyframes cheo-fade{0%{opacity:0}25%,100%{opacity:1}}
@keyframes cheo-heart{0%{transform:translate(0,0) scale(.2);opacity:0}18%{transform:translate(12%,-24%) scale(1);opacity:1}100%{transform:translate(64%,-130%) rotate(14deg) scale(.85);opacity:0}}
@keyframes cheo-happy{0%,100%{transform:translate(0,0) ${LEAN} scaleY(1)}25%,75%{transform:translate(0,calc(var(--_reach)*.4)) rotate(-14deg) scaleY(.18);border-radius:999px 999px 40% 40%}}
@media (prefers-reduced-motion:no-preference){
.eye{transition:transform 160ms ease-out,height 200ms ease,top 200ms ease}
.brow{transition:transform 200ms ease,top 200ms ease}
.orb{animation:cheo-morph 6s ease-in-out infinite,cheo-drift 10s ease-in-out infinite}
[data-live] .orb{animation:cheo-morph 2.2s ease-in-out infinite,cheo-breathe 1.5s ease-in-out infinite,cheo-drift 3s ease-in-out infinite}
[data-blink] .eye{animation:cheo-blink 4.8s ease-in-out infinite,cheo-glance 9s ease-in-out infinite}
[data-blink] .r{animation-delay:.12s,0s}
[data-mood=thinking] .eye{animation:cheo-think 2.6s ease-in-out infinite;transition:none}
[data-mood=happy] .eye{animation:cheo-happy 1.1s ease-in-out 1}
[data-mood=happy] .mouth{animation:cheo-smile 1.1s ease-out 1}
[data-mood=happy] .cheek{animation:cheo-fade 1.1s ease-out 1}
.ring{animation:cheo-ring 1.6s ease-out infinite}
.heart{animation:cheo-heart 1.6s ease-out infinite}
.h2{animation-delay:.8s}
}`;

// src/tracker.ts
var LOOK = /* @__PURE__ */ Symbol("cheo-look");
var REACH_PX = 240;
var clampUnit = (value) => Math.max(-1, Math.min(1, value));
function gazeOffset(dx, dy, max) {
  return [clampUnit(dx / REACH_PX) * max, clampUnit(dy / REACH_PX) * max];
}
var EVENTS = ["pointermove", "pointerdown", "focusin", "focusout", "input", "keyup", "selectionchange"];
var LISTENER_OPTIONS = { capture: true, passive: true };
var gazers = /* @__PURE__ */ new Set();
var pointer = null;
var frame = 0;
var reducedMotion;
var measure;
function track(gazer) {
  if (!gazers.size) {
    for (const type of EVENTS) window.addEventListener(type, handleEvent, LISTENER_OPTIONS);
    reducedMotion = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)") : void 0;
    reducedMotion?.addEventListener("change", schedule);
  }
  gazers.add(gazer);
  schedule();
}
function untrack(gazer) {
  if (!gazers.delete(gazer)) return;
  gazer[LOOK](null);
  if (gazers.size) return;
  for (const type of EVENTS) window.removeEventListener(type, handleEvent, LISTENER_OPTIONS);
  reducedMotion?.removeEventListener("change", schedule);
  reducedMotion = void 0;
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
}
function schedule() {
  if (!frame && gazers.size) frame = requestAnimationFrame(update);
}
function handleEvent(event) {
  if (event.type === "pointermove" || event.type === "pointerdown") {
    const { pointerType, clientX, clientY } = event;
    if (event.type === "pointermove" && pointerType === "touch") return;
    pointer = { x: clientX, y: clientY };
  }
  schedule();
}
function update() {
  frame = 0;
  const isStill = reducedMotion?.matches ?? false;
  for (const gazer of gazers) gazer[LOOK](isStill ? null : lookTarget(gazer));
}
function lookTarget(gazer) {
  const { mood, followTarget } = gazer;
  if (followTarget && (mood === "idle" || mood === "listening")) {
    const root = gazer.getRootNode();
    const target = querySafely(root, followTarget);
    const active = root.activeElement;
    if (target && active && target.contains(active)) return caretPoint(active);
  }
  return mood === "idle" ? pointer : null;
}
function querySafely(root, selector) {
  try {
    return root.querySelector(selector);
  } catch {
    return null;
  }
}
function caretPoint(element) {
  const rect = element.getBoundingClientRect();
  const center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    return fieldCaret(element, rect) ?? center;
  }
  const selection = getSelection();
  if (selection?.rangeCount && element.contains(selection.focusNode)) {
    const caret = selection.getRangeAt(0).getBoundingClientRect();
    if (caret.height) return { x: caret.right, y: caret.top + caret.height / 2 };
  }
  return center;
}
function fieldCaret(field, rect) {
  const position = field.selectionEnd;
  if (position == null) return null;
  measure ??= document.createElement("canvas").getContext("2d");
  if (!measure) return null;
  const style = getComputedStyle(field);
  measure.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const lines = field.value.slice(0, position).split("\n");
  const left = rect.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft);
  const x = Math.min(rect.right, left + measure.measureText(lines.at(-1) ?? "").width - field.scrollLeft);
  if (field instanceof HTMLInputElement) return { x, y: rect.top + rect.height / 2 };
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
  const top = rect.top + parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop);
  return { x, y: Math.min(rect.bottom, top + (lines.length - 0.5) * lineHeight - field.scrollTop) };
}

// src/element.ts
var CHEO_MOODS = ["idle", "listening", "thinking", "happy"];
var CHEO_COSTUMES = ["spooky", "santa", "mariachi"];
var CHEO_THEMES = ["light", "dark", "auto"];
var DEFAULT_SIZE = 56;
var DEFAULT_MOOD = "idle";
var DEFAULT_THEME = "light";
var DOT_BASE_SIZE = 24;
var PRESETS = {
  16: [2, 3, 0.8, 1],
  24: [2.8, 4.4, 1.2, 1.6],
  56: [5.5, 9.5, 3, 4]
};
var BROWS_MIN_SIZE = 32;
var PROPERTIES = ["size", "mood", "live", "follow", "followTarget", "ready", "theme", "blink", "awake", "label", "costume", "heart"];
var TEMPLATE = `<style>${STYLES}</style><span class="face"><span class="ring" part="ring"></span><span class="orb" part="orb"><span class="brow bl" part="brow"></span><span class="brow br" part="brow"></span><span class="eye l" part="eye"></span><span class="eye r" part="eye"></span><span class="cheek" part="cheek"></span><span class="mouth" part="mouth"></span><span class="stache" part="stache"></span></span><span class="hat" part="hat"></span><svg class="heart" part="heart" viewBox="0 0 24 22" aria-hidden="true"><path d="M12 21C6 16 1 12 1 7a5.6 5.6 0 0 1 11-1 5.6 5.6 0 0 1 11 1c0 5-5 9-11 14z"/></svg><svg class="heart h2" part="heart" viewBox="0 0 24 22" aria-hidden="true"><path d="M12 21C6 16 1 12 1 7a5.6 5.6 0 0 1 11-1 5.6 5.6 0 0 1 11 1c0 5-5 9-11 14z"/></svg><span class="dot" part="dot"></span></span>`;
var ElementBase = typeof HTMLElement === "undefined" ? class {
} : HTMLElement;
var CheoOrbElement = class extends ElementBase {
  static observedAttributes = ["size", "mood", "live", "follow", "follow-target", "ready", "theme", "blink", "awake", "label", "costume", "heart"];
  #face;
  #gazeReach = 0;
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE;
    this.#face = root.querySelector(".face");
  }
  connectedCallback() {
    for (const name of PROPERTIES) {
      if (!Object.prototype.hasOwnProperty.call(this, name)) continue;
      const value = this[name];
      Reflect.deleteProperty(this, name);
      Reflect.set(this, name, value);
    }
    this.#render();
  }
  disconnectedCallback() {
    untrack(this);
  }
  attributeChangedCallback() {
    this.#render();
  }
  /** Diameter in CSS px. 16, 24, and 56 keep the app's tuned eye geometry; other sizes scale from 56. */
  get size() {
    const value = Number(this.getAttribute("size"));
    return Number.isFinite(value) && value > 0 ? value : DEFAULT_SIZE;
  }
  set size(value) {
    setOrRemove(this, "size", value);
  }
  get mood() {
    return pick(CHEO_MOODS, this.getAttribute("mood"), DEFAULT_MOOD);
  }
  set mood(value) {
    setOrRemove(this, "mood", value);
  }
  /** An answer is streaming: the body breathes faster and a ring pulses out of it. */
  get live() {
    return this.hasAttribute("live");
  }
  set live(value) {
    this.toggleAttribute("live", Boolean(value));
  }
  /** The eyes follow the pointer anywhere on the page (idle only; off under reduced motion). */
  get follow() {
    return this.hasAttribute("follow");
  }
  set follow(value) {
    this.toggleAttribute("follow", Boolean(value));
  }
  /** CSS selector; while that element (or something inside it) has focus, the eyes look at its caret. */
  get followTarget() {
    return this.getAttribute("follow-target");
  }
  set followTarget(value) {
    setOrRemove(this, "follow-target", value);
  }
  /** The yellow answer-ready dot. */
  get ready() {
    return this.hasAttribute("ready");
  }
  set ready(value) {
    this.toggleAttribute("ready", Boolean(value));
  }
  get theme() {
    return pick(CHEO_THEMES, this.getAttribute("theme"), DEFAULT_THEME);
  }
  set theme(value) {
    setOrRemove(this, "theme", value);
  }
  /** The idle blink-and-glance loop. On unless the attribute is `blink="false"`. */
  get blink() {
    return this.getAttribute("blink") !== "false";
  }
  set blink(value) {
    if (value === false || value === "false") this.setAttribute("blink", "false");
    else this.removeAttribute("blink");
  }
  /** Wide-awake eyes (idle only), as when the app's Ask Cheo pill is hovered. Hovering the orb itself does the same. */
  get awake() {
    return this.hasAttribute("awake");
  }
  set awake(value) {
    this.toggleAttribute("awake", Boolean(value));
  }
  /** A costume drawn over the face: `spooky` (pumpkin cap), `santa` (Santa hat), or `mariachi` (sombrero and mustache). */
  get costume() {
    const value = this.getAttribute("costume");
    return CHEO_COSTUMES.includes(value) ? value : null;
  }
  set costume(value) {
    setOrRemove(this, "costume", value);
  }
  /** Yellow hearts float up out of the orb while on. */
  get heart() {
    return this.hasAttribute("heart");
  }
  set heart(value) {
    this.toggleAttribute("heart", Boolean(value));
  }
  /** Accessible name. Without one the orb is decorative (`aria-hidden`). */
  get label() {
    return this.getAttribute("label");
  }
  set label(value) {
    setOrRemove(this, "label", value);
  }
  [LOOK](point) {
    const style = this.#face.style;
    if (!point) {
      style.removeProperty("--_gaze-x");
      style.removeProperty("--_gaze-y");
      return;
    }
    const rect = this.#face.getBoundingClientRect();
    const [x, y] = gazeOffset(point.x - (rect.left + rect.width / 2), point.y - (rect.top + rect.height / 2), this.#gazeReach);
    style.setProperty("--_gaze-x", `${x.toFixed(2)}px`);
    style.setProperty("--_gaze-y", `${y.toFixed(2)}px`);
  }
  #render() {
    const { size, mood } = this;
    const preset = PRESETS[size];
    const scale = preset ? 1 : size / DEFAULT_SIZE;
    const [eyeWidth, eyeHeight, glanceReach, gazeReach] = preset ?? [5.5 * scale, 9.5 * scale, 3 * scale, 4 * scale];
    this.#gazeReach = gazeReach;
    const face = this.#face;
    const style = face.style;
    style.setProperty("--_size", `${size}px`);
    style.setProperty("--_k", String(scale));
    style.setProperty("--_d", String(size / DOT_BASE_SIZE));
    style.setProperty("--_eye-w", `${eyeWidth}px`);
    style.setProperty("--_eye-h", `${eyeHeight}px`);
    style.setProperty("--_reach", `${glanceReach}px`);
    face.dataset.mood = mood;
    face.toggleAttribute("data-live", this.live);
    face.toggleAttribute("data-ready", this.ready);
    face.toggleAttribute("data-awake", this.awake);
    face.toggleAttribute("data-brows", size >= BROWS_MIN_SIZE);
    face.toggleAttribute("data-heart", this.heart);
    const costume = this.costume;
    if (costume) face.dataset.costume = costume;
    else delete face.dataset.costume;
    face.toggleAttribute("data-blink", this.blink && (mood === "idle" || mood === "listening"));
    if (!this.isConnected) return;
    this.#syncAria();
    if (this.follow) track(this);
    else untrack(this);
  }
  #syncAria() {
    const label = this.label;
    if (label) {
      this.setAttribute("role", "img");
      this.setAttribute("aria-label", label);
      this.removeAttribute("aria-hidden");
      return;
    }
    if (this.getAttribute("role") === "img") {
      this.removeAttribute("role");
      this.removeAttribute("aria-label");
    }
    this.setAttribute("aria-hidden", "true");
  }
};
function pick(allowed, value, fallback) {
  return allowed.includes(value) ? value : fallback;
}
function setOrRemove(element, name, value) {
  if (value == null || value === "") element.removeAttribute(name);
  else element.setAttribute(name, String(value));
}

// src/index.ts
var DEFAULT_TAG_NAME = "cheo-orb";
function defineCheoOrb(tagName = DEFAULT_TAG_NAME) {
  if (typeof customElements === "undefined") return void 0;
  registerGlanceProperty();
  const existing = customElements.get(tagName);
  if (existing) return existing;
  const element = class extends CheoOrbElement {
  };
  customElements.define(tagName, element);
  return element;
}
function registerGlanceProperty() {
  if (typeof CSS === "undefined" || typeof CSS.registerProperty !== "function") return;
  try {
    CSS.registerProperty({ name: GLANCE_PROPERTY, syntax: "<length>", inherits: true, initialValue: "0px" });
  } catch {
  }
}
defineCheoOrb();
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  CHEO_COSTUMES,
  CHEO_MOODS,
  CHEO_THEMES,
  CheoOrbElement,
  DEFAULT_TAG_NAME,
  defineCheoOrb,
  gazeOffset
});
//# sourceMappingURL=index.cjs.map