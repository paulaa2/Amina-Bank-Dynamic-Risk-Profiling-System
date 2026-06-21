"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  ScrollText,
  ShieldCheck,
  Network,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV_ITEMS = [
  { label: "Control Room",    href: "/",        icon: LayoutDashboard },
  { label: "Client Dossiers", href: "/client",  icon: FolderOpen      },
  { label: "Demo Studio",     href: "/demos",   icon: Network         },
  { label: "Audit History",   href: "/history", icon: ScrollText      },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-800 bg-slate-950">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-800 px-5">
        <ShieldCheck className="h-5 w-5 text-slate-400" strokeWidth={1.75} />
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500">
            AMINA Bank
          </p>
          <p className="text-sm font-semibold text-slate-200 leading-tight">
            Risk Intelligence
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 px-3 py-4">
        <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
          Navigation
        </p>
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-500 hover:bg-slate-800/60 hover:text-slate-200"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="mt-auto space-y-3 border-t border-slate-800 px-5 py-4">
        <ThemeToggle />
        <p className="text-[11px] text-slate-500">
          pKYC Engine v1.0 · SwissHacks 2026
        </p>
        <p className="text-[10px] text-slate-600 mt-0.5">
          Confidential — Internal Use Only
        </p>
      </div>
    </aside>
  );
}
