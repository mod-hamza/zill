import { Fraunces, Inter_Tight } from "next/font/google";

// next/font downloads at build time and self-hosts: no runtime CDN.
export const display = Fraunces({
  subsets: ["latin"],
  weight: "variable",
  axes: ["opsz"],
  variable: "--font-display",
  display: "swap",
});

export const ui = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ui",
  display: "swap",
});
