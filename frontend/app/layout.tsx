import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { LogoutButton } from "@/components/logout-button";
import { MailboxNavItem } from "@/components/mailbox-nav-item";
import { Toaster } from "@/components/toaster";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kwabo Order Intake AI",
  description: "Review-dashboard voor inkomende orders",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="nl" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="bg-[var(--kwabo-navy)] text-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="flex items-center gap-3">
              <span className="logo-pill">
                <Image
                  src="/kwabo-logo.png"
                  alt="Kwabo"
                  width={120}
                  height={36}
                  priority
                  className="h-8 w-auto"
                />
              </span>
              <span className="hidden text-sm font-medium uppercase tracking-[0.2em] text-white/80 sm:inline">
                Order Intake <span className="text-[var(--kwabo-gold)]">· AI</span>
              </span>
            </Link>
            <nav className="flex gap-6 text-sm font-medium text-white/80">
              <Link href="/" className="hover:text-white">Queue</Link>
              <Link href="/klanten" className="hover:text-white">Klanten</Link>
              <MailboxNavItem />
              <Link href="/audit" className="hover:text-white">Audit</Link>
              <Link href="/logs" className="hover:text-white">Logs</Link>
              <Link href="/configuratie" className="hover:text-white">Configuratie</Link>
              <LogoutButton />
            </nav>
          </div>
          <div className="kwabo-header-accent" />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">{children}</main>
        <footer className="border-t border-[var(--kwabo-border)] bg-white py-3 text-center text-xs text-[var(--kwabo-muted)]">
          © Kwabo Techniek B.V. · Order Intake AI
        </footer>
        <Toaster />
      </body>
    </html>
  );
}
