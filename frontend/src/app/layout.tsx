import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { NAME, TAGLINE } from "@/brand";
import { display, ui } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: `${NAME} | ${TAGLINE}`,
  description: TAGLINE,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${ui.variable}`}>
      <body>
        {children}
        <Footer />
      </body>
    </html>
  );
}
