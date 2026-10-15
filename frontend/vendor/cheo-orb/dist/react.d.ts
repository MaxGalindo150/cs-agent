import * as react from 'react';
import { DetailedHTMLProps, HTMLAttributes } from 'react';
import { CheoOrbElement, CheoMood, CheoTheme, CheoCostume } from '@cashea/cheo';
export { CheoCostume, CheoMood, CheoOrbElement, CheoTheme } from '@cashea/cheo';

interface CheoOrbProps extends Omit<HTMLAttributes<CheoOrbElement>, 'children'> {
    /** Diameter in CSS px (default 56). 16, 24, and 56 keep the app's tuned eye geometry; other sizes scale from 56. */
    size?: number;
    /** What the face is doing (default `idle`). */
    mood?: CheoMood;
    /** An answer is streaming: faster morph, breathing, and the pulsing ring. */
    live?: boolean;
    /** The eyes follow the pointer anywhere on the page (idle only; off under reduced motion). */
    follow?: boolean;
    /** CSS selector; while that element has focus, the eyes look at its caret. Needs `follow`. */
    followTarget?: string;
    /** The yellow answer-ready dot. */
    ready?: boolean;
    /** `light` (default), `dark`, or `auto` (follows `prefers-color-scheme`). */
    theme?: CheoTheme;
    /** The idle blink-and-glance loop (default `true`). */
    blink?: boolean;
    /** Wide-awake eyes, e.g. while a surrounding button is hovered. */
    awake?: boolean;
    /** Accessible name. Without one the orb is decorative (`aria-hidden`). */
    label?: string;
    /** A costume over the face: `spooky`, `santa`, or `mariachi`. */
    costume?: CheoCostume;
    /** Yellow hearts float up out of the orb while on. */
    heart?: boolean;
}
/**
 * Cheo for React. Renders `<cheo-orb>`; boolean props become present-or-absent attributes,
 * which React 18 and 19 both handle the same way.
 */
declare const CheoOrb: react.ForwardRefExoticComponent<CheoOrbProps & react.RefAttributes<CheoOrbElement>>;
/** Attributes of `<cheo-orb>` when written directly in JSX. */
interface CheoOrbIntrinsicAttributes extends DetailedHTMLProps<HTMLAttributes<CheoOrbElement>, CheoOrbElement> {
    class?: string;
    size?: number | string;
    mood?: CheoMood;
    live?: boolean;
    follow?: boolean;
    'follow-target'?: string;
    ready?: boolean;
    theme?: CheoTheme;
    blink?: boolean | 'true' | 'false';
    awake?: boolean;
    label?: string;
    costume?: CheoCostume;
    heart?: boolean;
}
declare module 'react' {
    namespace JSX {
        interface IntrinsicElements {
            'cheo-orb': CheoOrbIntrinsicAttributes;
        }
    }
}

export { CheoOrb, type CheoOrbIntrinsicAttributes, type CheoOrbProps };
