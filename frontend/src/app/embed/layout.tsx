import type { Metadata } from "next";
import { Open_Sans } from "next/font/google";

// Luz's body face (merchant-web), exposed as the variable .theme-cashea reads.
const openSans = Open_Sans({
  variable: "--font-open-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Soporte Cashea",
};

/**
 * Shell for the widget as a host page embeds it: rendered inside the iframe
 * that public/widget.js injects, in the light Cashea theme (see .theme-cashea
 * in globals.css).
 */
export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${openSans.variable} theme-cashea h-full bg-background text-foreground`}>
      {children}
    </div>
  );
}
