import type { Metadata } from "next";
import { Fraunces, Source_Sans_3 } from "next/font/google";
import "./globals.css";

const sourceSans = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-source",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "Transcript Intelligence",
  description:
    "Executive briefing over Aegis Cloud call transcripts: themes, sentiment, and stakeholder insights.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sourceSans.variable} ${fraunces.variable} h-full antialiased`}
      style={{ colorScheme: "light" }}
    >
      <body className="min-h-full bg-background font-sans text-foreground">{children}</body>
    </html>
  );
}
