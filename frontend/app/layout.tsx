import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TerreX // Geospatial Intelligence at Scale",
  description:
    "Offline, AI-powered satellite imagery search and bi-temporal change detection platform. Natural language semantic search, Prithvi-EO feature difference, and automated false-alarm suppression with zero cloud egress.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <body className="bg-black text-white antialiased selection:bg-white selection:text-black">
        {children}
      </body>
    </html>
  );
}
