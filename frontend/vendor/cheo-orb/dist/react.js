"use client";

// src/react.tsx
import { forwardRef } from "react";
import "@cashea/cheo";
import { jsx } from "react/jsx-runtime";
var CheoOrb = forwardRef(function CheoOrb2({ size, mood, live, follow, followTarget, ready, theme, blink, awake, label, costume, heart, className, ...rest }, ref) {
  return /* @__PURE__ */ jsx(
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
export {
  CheoOrb
};
//# sourceMappingURL=react.js.map