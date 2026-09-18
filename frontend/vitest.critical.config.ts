import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Срез-229: псевдоним `@/*` разбирает сам сборщик (vite 8), плагин снят.
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./vitest.setup.ts",
    css: true,
    api: false,
    exclude: [...configDefaults.exclude, "**/e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: [
        "src/components/layout/**/*.tsx",
        "src/router/**/*.ts",
        "src/router/**/*.tsx",
        "src/pages/documents/DocumentsPage.tsx",
        "src/pages/tasks/TasksPage.tsx",
        "src/pages/packs/PacksPage.tsx",
      ],
      thresholds: {
        lines: 70,
        branches: 55,
        statements: 70,
      },
    },
  },
});
