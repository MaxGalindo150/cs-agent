interface Point {
    x: number;
    y: number;
}
/** Called once per frame with where the eyes should look, or `null` to look ahead. */
declare const LOOK: unique symbol;
/** Eye offset in px for a point `dx, dy` away from the face center, at most `max` on each axis. */
declare function gazeOffset(dx: number, dy: number, max: number): [number, number];

declare const CHEO_MOODS: readonly ["idle", "listening", "thinking", "happy"];
/** What the face is doing. The body keeps morphing whatever the mood. */
type CheoMood = (typeof CHEO_MOODS)[number];
declare const CHEO_COSTUMES: readonly ["spooky", "santa", "mariachi"];
/** A hat (and, for `mariachi`, a mustache) drawn over the face. */
type CheoCostume = (typeof CHEO_COSTUMES)[number];
declare const CHEO_THEMES: readonly ["light", "dark", "auto"];
/** `auto` follows `prefers-color-scheme`. */
type CheoTheme = (typeof CHEO_THEMES)[number];
/** Lets the module load where `HTMLElement` does not exist (SSR, workers); it is never constructed there. */
declare const ElementBase: typeof HTMLElement;
/**
 * Cheo: a slowly morphing white blob with an ink outline, arched brows, and two leaning ink eyes that
 * blink on their own clock, follow the pointer, narrow while an answer is written,
 * drop toward the composer when someone types, and squint (with a grin) when it lands.
 * Pure CSS apart from the gaze; still under reduced motion.
 */
declare class CheoOrbElement extends ElementBase {
    #private;
    static readonly observedAttributes: string[];
    constructor();
    connectedCallback(): void;
    disconnectedCallback(): void;
    attributeChangedCallback(): void;
    /** Diameter in CSS px. 16, 24, and 56 keep the app's tuned eye geometry; other sizes scale from 56. */
    get size(): number;
    set size(value: number | string | null | undefined);
    get mood(): CheoMood;
    set mood(value: CheoMood | null | undefined);
    /** An answer is streaming: the body breathes faster and a ring pulses out of it. */
    get live(): boolean;
    set live(value: boolean | null | undefined);
    /** The eyes follow the pointer anywhere on the page (idle only; off under reduced motion). */
    get follow(): boolean;
    set follow(value: boolean | null | undefined);
    /** CSS selector; while that element (or something inside it) has focus, the eyes look at its caret. */
    get followTarget(): string | null;
    set followTarget(value: string | null | undefined);
    /** The yellow answer-ready dot. */
    get ready(): boolean;
    set ready(value: boolean | null | undefined);
    get theme(): CheoTheme;
    set theme(value: CheoTheme | null | undefined);
    /** The idle blink-and-glance loop. On unless the attribute is `blink="false"`. */
    get blink(): boolean;
    set blink(value: boolean | 'true' | 'false' | null | undefined);
    /** Wide-awake eyes (idle only), as when the app's Ask Cheo pill is hovered. Hovering the orb itself does the same. */
    get awake(): boolean;
    set awake(value: boolean | null | undefined);
    /** A costume drawn over the face: `spooky` (pumpkin cap), `santa` (Santa hat), or `mariachi` (sombrero and mustache). */
    get costume(): CheoCostume | null;
    set costume(value: CheoCostume | null | undefined);
    /** Yellow hearts float up out of the orb while on. */
    get heart(): boolean;
    set heart(value: boolean | null | undefined);
    /** Accessible name. Without one the orb is decorative (`aria-hidden`). */
    get label(): string | null;
    set label(value: string | null | undefined);
    [LOOK](point: Point | null): void;
}

declare const DEFAULT_TAG_NAME = "cheo-orb";
/**
 * Registers the element under `tagName` (default `cheo-orb`) and returns its constructor.
 * Safe to call any number of times, from any number of copies of this package, and on
 * the server, where it does nothing and returns `undefined`.
 */
declare function defineCheoOrb(tagName?: string): typeof CheoOrbElement | undefined;
declare global {
    interface HTMLElementTagNameMap {
        'cheo-orb': CheoOrbElement;
    }
}

export { CHEO_COSTUMES, CHEO_MOODS, CHEO_THEMES, type CheoCostume, type CheoMood, CheoOrbElement, type CheoTheme, DEFAULT_TAG_NAME, defineCheoOrb, gazeOffset };
