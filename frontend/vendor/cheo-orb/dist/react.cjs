"use strict";
"use client";
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

// src/react.tsx
var react_exports = {};
__export(react_exports, {
  CheoOrb: () => CheoOrb
});
module.exports = __toCommonJS(react_exports);
var import_react = require("react");
var import_cheo = require("@cashea/cheo");
var import_jsx_runtime = require("react/jsx-runtime");
var CheoOrb = (0, import_react.forwardRef)(function CheoOrb2({ size, mood, live, follow, followTarget, ready, theme, blink, awake, label, costume, heart, className, ...rest }, ref) {
  return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
    "cheo-orb",
    {
      ref,
      ...rest,
      class: className,
      size,
      mood,
      theme,
      label,
      costume,
      "follow-target": followTarget,
      heart: heart || void 0,
      live: live || void 0,
      follow: follow || void 0,
      ready: ready || void 0,
      awake: awake || void 0,
      blink: blink === false ? "false" : void 0
    }
  );
});
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  CheoOrb
});
//# sourceMappingURL=react.cjs.map