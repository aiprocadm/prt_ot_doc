import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { UX_BUDGET_OUT_OF_SCOPE } from "@/test-utils/uxBudgetScope";

/**
 * Полнота приёмки экранов (ТЗ разд. 59.2, 60).
 *
 * До этого сторожа полнота жила фразой в отчёте («81 из 82»), и фраза
 * протухла молча: новых экранов появилось полтора десятка, а по документу
 * это было не видно. Теперь у каждого экрана есть ровно два законных
 * состояния — «замерен» или «названа причина, почему не мерим».
 */

const PAGES_DIR = join(process.cwd(), "src", "pages");
const TESTS_DIRS = [join(process.cwd(), "src", "__tests__"), PAGES_DIR];

const walk = (dir: string): string[] => {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...walk(full));
      continue;
    }
    out.push(full);
  }
  return out;
};

const pageNames = (): string[] =>
  walk(PAGES_DIR)
    .filter((f) => f.endsWith("Page.tsx") && !f.endsWith(".test.tsx"))
    .map((f) =>
      f
        .split("/")
        .pop()!
        .replace(/\.tsx$/, ""),
    )
    .sort();

const measuredScreens = (): Set<string> => {
  const measured = new Set<string>();
  for (const dir of TESTS_DIRS) {
    for (const file of walk(dir)) {
      if (!file.endsWith(".test.tsx") && !file.endsWith(".test.ts")) continue;
      const source = readFileSync(file, "utf-8");
      for (const match of source.matchAll(
        /uxBudgetDelta\([^,]+,\s*"([^"]+)"/g,
      )) {
        measured.add(match[1]);
      }
    }
  }
  return measured;
};

describe("полнота приёмки UX-бюджета", () => {
  it("у каждого экрана есть замер или названа причина, почему его нет", () => {
    const measured = measuredScreens();
    const безЗамера = pageNames().filter(
      (name) => !measured.has(name) && !(name in UX_BUDGET_OUT_OF_SCOPE),
    );

    expect(безЗамера).toEqual([]);
  });

  it("исключение снимается, как только появился замер", () => {
    const measured = measuredScreens();
    const протухшие = Object.keys(UX_BUDGET_OUT_OF_SCOPE).filter((name) =>
      measured.has(name),
    );

    expect(протухшие).toEqual([]);
  });

  it("исключение объясняется словами, а не отговоркой", () => {
    for (const [screen, reason] of Object.entries(UX_BUDGET_OUT_OF_SCOPE)) {
      expect(reason.trim().length, screen).toBeGreaterThan(20);
    }
  });
});
