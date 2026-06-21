import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

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
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(() => {
              try {
                const mode = localStorage.getItem("amina-theme") === "light" ? "light" : "dark";
                document.documentElement.classList.toggle("light", mode === "light");
                document.documentElement.classList.toggle("dark", mode === "dark");
                document.documentElement.dataset.theme = mode;
              } catch {}
            })();`,
          }}
        />
      </head>
      <body className="app-shell bg-slate-950 text-slate-200 antialiased">
        <Sidebar />
        <main className="ml-60 min-h-screen">{children}</main>
      </body>
    </html>
  );
}
