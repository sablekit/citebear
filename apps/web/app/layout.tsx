import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CiteBear — source-cited answers",
  description:
    "Ask questions about a document library and get streaming answers that cite their sources — or an honest \"I don't know.\"",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {children}
        <footer className="border-t border-zinc-200 px-4 py-3 text-center text-xs text-zinc-400 dark:border-zinc-800 dark:text-zinc-500">
          Questions are logged to improve answer quality. No accounts, no cookies, IPs are hashed.
        </footer>
        <Analytics />
      </body>
    </html>
  );
}
