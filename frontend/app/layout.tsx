import type { Metadata } from "next";
import { DM_Sans, Space_Mono } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const sans = DM_Sans({ subsets: ["latin"], variable: "--font-sans" });
const mono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: { default: "ScanTheDoc", template: "%s — ScanTheDoc" },
  description: "Upload, search and process documents.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
