import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AMINA Bank — Risk Intelligence",
  description:
    "Dynamic Risk Profiling System — KYC Drift Detection & AML Compliance",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-slate-950 text-slate-200 antialiased">
        <Sidebar />
        <main className="ml-60 min-h-screen">{children}</main>
      </body>
    </html>
  );
}
