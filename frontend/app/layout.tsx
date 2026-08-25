import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerWright — Reconciliation Dashboard",
  description: "AI reconciliation agent that closes the books for small businesses",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-slate-900 antialiased">{children}</body>
    </html>
  );
}