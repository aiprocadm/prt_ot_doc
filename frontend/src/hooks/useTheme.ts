import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "prt-theme";

export const useTheme = (): [Theme, (theme: Theme) => void, () => void] => {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove(theme === "dark" ? "light" : "dark");
    root.classList.add(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = () => setTheme((prev) => (prev === "light" ? "dark" : "light"));

  return [theme, setTheme, toggle];
};
