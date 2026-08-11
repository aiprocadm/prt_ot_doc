import { useEffect, useState } from "react";
import {
  localStorageGetItem,
  localStorageSetItem,
} from "@/utils/browserStorage";

type Theme = "light" | "dark";
const STORAGE_KEY = "prt-theme";

const detectPreferredTheme = (): Theme => {
  if (typeof window === "undefined") return "light";
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  } catch {
    return "light";
  }
};

export const useTheme = (): [Theme, (theme: Theme) => void, () => void] => {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorageGetItem(STORAGE_KEY) as Theme | null;
    if (stored) return stored;
    return detectPreferredTheme();
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove(theme === "dark" ? "light" : "dark");
    root.classList.add(theme);
    localStorageSetItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = () =>
    setTheme((prev) => (prev === "light" ? "dark" : "light"));

  return [theme, setTheme, toggle];
};
