import { useEffect } from "react";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "plutus-theme";

export function getStoredTheme(): ThemeMode {
  return (localStorage.getItem(STORAGE_KEY) as ThemeMode) || "dark";
}

export function applyTheme(mode: ThemeMode) {
  const isDark =
    mode === "dark" ||
    (mode === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);

  document.documentElement.classList.toggle("dark", isDark);
  localStorage.setItem(STORAGE_KEY, mode);
}

export function useTheme(mode: ThemeMode) {
  useEffect(() => {
    applyTheme(mode);
  }, [mode]);

  // Listen for system theme changes when in "system" mode
  useEffect(() => {
    if (mode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [mode]);
}
