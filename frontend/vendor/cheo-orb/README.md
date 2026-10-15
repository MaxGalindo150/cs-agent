# @cashea/cheo

Cheo, the Cashea assistant orb, as a framework-free `<cheo-orb>` custom element: a white morphing body with an ink outline, arched brows over leaning eyes that blink and follow the pointer, and a grin when an answer lands. Every state is covered by a visual regression test.

- One self-registering script, under 6 KB gzipped, with no dependencies.
- Shadow DOM, so page styles cannot break it and it cannot leak styles into the page.
- An optional React wrapper for React and Next.js.

## Plain HTML and Webflow

Add the script once, then use the element anywhere:

```html
<script src="https://cdn.jsdelivr.net/npm/@cashea/cheo@0.1.0/dist/cheo-orb.js" defer></script>

<cheo-orb></cheo-orb>
<cheo-orb size="24" mood="thinking" live></cheo-orb>
<cheo-orb size="96" follow label="Cheo, el asistente de Cashea"></cheo-orb>
```

In Webflow, put the `<script>` in **Site settings → Custom code → Footer code** (or a page's footer code), and the `<cheo-orb>` tags in an **Embed** element. Pin an exact version (`@0.1.0`) so the site never changes under you; `@0.1` takes compatible updates automatically.

Change the orb from a script by setting properties:

```js
const cheo = document.querySelector('cheo-orb');
cheo.mood = 'listening';
cheo.live = true;
```

## npm (bundlers, Vite, plain ES modules)

```sh
npm install @cashea/cheo
```

```ts
import '@cashea/cheo'; // registers <cheo-orb>

const cheo = document.createElement('cheo-orb');
cheo.size = 24;
cheo.mood = 'thinking';
cheo.live = true;
document.body.append(cheo);
```

To register under another tag name, call `defineCheoOrb('my-cheo')`. It is safe to call more than once, and it does nothing on the server.

## React and Next.js

```tsx
import { CheoOrb } from '@cashea/cheo/react';

export function AskCheoHeader({ isStreaming, hasUnseenAnswer }: { isStreaming: boolean; hasUnseenAnswer: boolean }) {
  return (
    <CheoOrb
      size={24}
      mood={isStreaming ? 'thinking' : 'idle'}
      live={isStreaming}
      ready={hasUnseenAnswer && !isStreaming}
    />
  );
}
```

`@cashea/cheo/react` is a client module (`'use client'`), so it works from Next.js Server Components without extra wrapping. It server-renders as a plain `<cheo-orb>` tag and the element takes over in the browser. The ref is the `CheoOrbElement`. React 18 and 19 are supported; React is an optional peer dependency, needed only for this entry point.

Importing `@cashea/cheo/react` also types `<cheo-orb>` for JSX, if you would rather write the element directly.

## Attributes

Every attribute is also a property (`follow-target` is `followTarget`). Setting a property updates the attribute, and the reverse.

| Attribute | Values | Default | What it does |
| --- | --- | --- | --- |
| `size` | number, in CSS px | `56` | Diameter. 16, 24, and 56 keep the tuned eye geometry; any other size is the 56 px face scaled, shadow included. Below 32 px the brows are left out. |
| `mood` | `idle`, `listening`, `thinking`, `happy` | `idle` | What the face is doing (see below). The body keeps morphing in every mood. |
| `live` | boolean | off | An answer is streaming: faster morph, a gentle breath, and a ring pulsing out of the orb. |
| `follow` | boolean | off | The eyes follow the pointer anywhere on the page while idle. On touch screens they look toward the last tap. |
| `follow-target` | CSS selector | none | With `follow`, while the matching element (or anything inside it) has focus, the eyes look at its caret. Use it for a chat input. |
| `ready` | boolean | off | The answer-ready dot in the top-right corner, ringed in `--cheo-bg`. |
| `theme` | `light`, `dark`, `auto` | `light` | Which brand palette to use. `auto` follows the visitor's `prefers-color-scheme`. |
| `blink` | `blink="false"` turns it off | on | The idle loop: a blink every 4.8 s and a glance every 9 s. |
| `awake` | boolean | off | Wide-awake eyes (1.2× taller) while idle, for when a surrounding button is hovered. Hovering the orb itself does the same on devices with a mouse. |
| `label` | text | none | The accessible name. Without it the orb is decorative. |
| `costume` | `spooky`, `santa`, `mariachi` | none | A hat drawn over the face (see below). It sticks out above the element, so give it headroom and avoid `overflow: hidden` on the parent. |
| `heart` | boolean | off | Two yellow hearts float up out of the orb, one after the other, while on. Combine with `mood="happy"` to send love. |

Boolean attributes are on when present (`<cheo-orb live>`) and off when absent. `blink` is the exception because it defaults to on.

### Moods

| Mood | Looks like | When to use it |
| --- | --- | --- |
| `idle` | Eyes open, blinking and glancing; follows the pointer with `follow`; brows lift with `awake` or on hover | Resting |
| `listening` | Eyes drop and open a little wider, brows lift | Someone is typing in the composer |
| `thinking` | Eyes narrowed, looking up from side to side, brows knitted | An answer is streaming (always with `live`) |
| `happy` | A 1.1 s squint and a grin (with a cheek crease) that stays while the mood is `happy` | An answer just landed |

`happy` plays its squint each time the mood changes to `happy`. Switch back to `idle` afterwards and show `ready` until the answer is seen.

### Costumes

| Costume | Looks like |
| --- | --- |
| `spooky` | An orange pumpkin cap with a green stem, for Halloween |
| `santa` | A red Santa hat with a white band and pom, for December |
| `mariachi` | A yellow sombrero with a black band, and a handlebar mustache |

Costumes combine with every mood and with `heart`. Their colors are `--cheo-orange`, `--cheo-green` and `--cheo-red` (the sombrero uses `--cheo-accent`); override them like the brand tokens below.

## Colors and styling

The brand colors are CSS custom properties, so a host can retint Cheo without touching the package:

```css
cheo-orb {
  --cheo-body: #fefefe;   /* the body */
  --cheo-ink: #0a0a0a;    /* outline, brows, eyes and mouth */
  --cheo-accent: #fdfa3d; /* glow, live ring, ready dot */
  --cheo-bg: #fefefe;     /* the page background, used to ring the ready dot */
}
```

| Property | Light | Dark |
| --- | --- | --- |
| `--cheo-body` | `#FEFEFE` | `#FEFEFE` |
| `--cheo-ink` | `#0A0A0A` | `#0A0A0A` |
| `--cheo-accent` | `#FDFA3D` | `#FDFC8A` |
| `--cheo-bg` | `#FEFEFE` | `#0A0A0A` |

A value you set wins in every theme. To retint per theme, scope it yourself, for example `.dark cheo-orb { --cheo-accent: … }`. Set `--cheo-bg` to your page background if you use `ready` on a background other than these.

The internal parts can be styled with `::part()`: `cheo-orb::part(orb)`, `::part(eye)`, `::part(brow)`, `::part(mouth)`, `::part(cheek)`, `::part(hat)`, `::part(stache)`, `::part(heart)`, `::part(ring)`, and `::part(dot)`.

`cheo-orb` is `display: inline-flex`. To reserve its space before the script loads, add `cheo-orb:not(:defined) { display: inline-block; width: 56px; height: 56px; }` (with your size).

## Accessibility

By default Cheo is decorative: the element gets `aria-hidden="true"`, which is right when it sits next to a visible "Ask Cheo" label. When the orb is the only thing that says what a control is, give it a name with `label`; it then gets `role="img"` and that `aria-label`:

```html
<button type="button"><cheo-orb size="24" label="Ask Cheo"></cheo-orb></button>
```

Cheo never takes focus and never handles clicks; put it inside your own button or link.

## Reduced motion

When the visitor has asked for less motion (`prefers-reduced-motion: reduce`), every animation stops and the eyes stop following the pointer. The eyes still sit where each mood puts them (higher while thinking, lower and wider while listening), just without movement. It updates live if the visitor changes the setting.

## Following the pointer

All orbs with `follow` share one passive `pointermove` listener on `window`, throttled to one update per animation frame. It is added when the first following orb connects and removed when the last one disconnects or drops `follow`. The eyes reach full deflection when the pointer is about 240 px away, and never leave the face.

`follow-target` is resolved inside the same document or shadow root as the orb. For an `<input>` or `<textarea>`, the caret position is measured from the text before it; for other elements (such as `contenteditable`), from the current selection.

## Browser support

Current Chrome, Edge, Safari, and Firefox: anything with CSS `color-mix()` (Chrome and Edge 111, Safari 16.2, Firefox 113). The eased glance uses `CSS.registerProperty` where available; elsewhere the glance simply steps.

## Development

```sh
pnpm install
pnpm demo          # builds, then serves the demo at http://127.0.0.1:4173/demo/
pnpm test          # unit tests (Vitest + happy-dom)
pnpm build         # dist/: ESM + CJS + types, and the self-registering dist/cheo-orb.js
pnpm size          # fails if dist/cheo-orb.js is over 6 KB gzipped
pnpm test:visual   # visual regression (needs pnpm build and Playwright's Chromium)
pnpm test:visual:update  # rewrites test/visual/baselines from the current look
pnpm check         # typecheck, lint, unit tests, build, size
pnpm emoji         # animated Slack emoji (128 px GIFs, every mood and costume) in emoji/, needs pnpm build and ffmpeg
```

The visual regression test renders every state (idle, blink, awake, listening, thinking with its ring, happy, answer ready, hearts, and the three costumes; light and dark) at 1024 px and compares it with the reference renders in `test/visual/baselines/`, with the animations frozen at fixed poses. The test fails if more than 0.1% of the pixels differ. It runs in CI inside the matching Playwright container. After an intentional change to the look, regenerate the baselines inside that same container so the renders match CI's Chromium, then commit them:

```sh
pnpm build
docker run --rm -v "$PWD":/work -v cheo-orb-node-modules:/work/node_modules -w /work \
  mcr.microsoft.com/playwright:v1.63.0-noble \
  sh -c 'corepack enable && pnpm install --frozen-lockfile && pnpm build && pnpm test:visual:update'
```

The look lives in `src/styles.ts`.

## Releasing

1. `npm version patch` (or `minor` / `major`) bumps `package.json`, commits, and tags `vX.Y.Z`.
2. `git push --follow-tags`.

The **Release** workflow checks the tag against `package.json`, runs `pnpm check`, and publishes to npm with the `NPM_TOKEN` repository secret. It adds npm provenance only when this repository is public, because npm rejects provenance from private repositories. jsDelivr serves a new version within a few minutes of publishing.

## License

Proprietary. Copyright Cashea, all rights reserved. The package is publicly downloadable so Cashea sites can load it, but Cheo is a Cashea brand asset; see [LICENSE](./LICENSE).
