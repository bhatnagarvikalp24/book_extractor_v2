import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PDF Book Metadata Extractor",
  description: "Upload PDFs and extract book metadata automatically",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
