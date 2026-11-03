import type { Metadata } from "next";
import { Barlow_Condensed, IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { AppProvider } from "@/lib/league-context";
import { AppearanceProvider } from "@/lib/appearance";
import { bootScript } from "@/lib/themes";
import { Shell } from "@/components/shell";

// A sports-page type system: condensed headlines, a plain readable body face, tabular mono numbers (and a serif option).
const cond = Barlow_Condensed({ variable: "--font-cond", subsets: ["latin"], weight: ["500", "600", "700"] });
const body = IBM_Plex_Sans({ variable: "--font-body", subsets: ["latin"], weight: ["400", "500", "600"] });
const num = IBM_Plex_Mono({ variable: "--font-num", subsets: ["latin"], weight: ["400", "500", "600"] });
const serif = Source_Serif_4({ variable: "--font-serif", subsets: ["latin"], weight: ["600", "700"] });

export const metadata: Metadata = {
  title: "FantaBall",
  description: "Draft, manage and analyse your fantasy basketball league with real NBA data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${cond.variable} ${body.variable} ${num.variable} ${serif.variable}`}>
      <head>
        {/* applies the saved theme before first paint (static string built from src/lib/themes.ts; no user input is interpolated) */}
        <script dangerouslySetInnerHTML={{ __html: bootScript() }} />
      </head>
      <body>
        <AppearanceProvider><AppProvider><Shell>{children}</Shell></AppProvider></AppearanceProvider>
      </body>
    </html>
  );
}
