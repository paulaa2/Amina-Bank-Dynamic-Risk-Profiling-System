"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

type ThemeMode = "dark" | "light";

function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  root.classList.toggle("dark", mode === "dark");
  root.classList.toggle("light", mode === "light");
  root.dataset.theme = mode;
  localStorage.setItem("amina-theme", mode);
  window.dispatchEvent(new Event("amina-theme-change"));
}

export function ThemeToggle() {
  const mode = useSyncExternalStore(
    (onStoreChange) => {
      window.addEventListener("amina-theme-change", onStoreChange);
      window.addEventListener("storage", onStoreChange);
      return () => {
        window.removeEventListener("amina-theme-change", onStoreChange);
        window.removeEventListener("storage", onStoreChange);
      };
    },
    () => localStorage.getItem("amina-theme") === "light" ? "light" : "dark",
    () => "dark",
  );

  function toggleMode() {
    const next = mode === "dark" ? "light" : "dark";
    applyTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggleMode}
      className={cn(
        "inline-flex h-8 w-full items-center justify-between border px-2.5 text-xs font-medium transition-colors",
        "border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-100",
      )}
      aria-label="Toggle color mode"
    >
      <span>{mode === "dark" ? "Dark mode" : "Light mode"}</span>
      {mode === "dark" ? (
        <Moon className="h-4 w-4" strokeWidth={1.75} />
      ) : (
        <Sun className="h-4 w-4" strokeWidth={1.75} />
      )}
    </button>
  );
}
