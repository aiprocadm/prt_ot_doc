import { fileURLToPath } from "node:url";

import { defineConfig, type UserConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import tsconfigPaths from "vite-tsconfig-paths";

const manualChunks: NonNullable<UserConfig["build"]>["rollupOptions"] extends {
  output?: { manualChunks?: infer T };
}
  ? T
  : never = (id) => {
  if (!id.includes("node_modules")) {
    return undefined;
  }

  // Все зависимости — одним куском.
  //
  // Прежняя разбивка на vendor-react / vendor-ui / vendor-state / ... была
  // сделана по подстроке в пути, из-за чего react-hook-form, react-i18next,
  // lucide-react и @radix-ui/react-* попадали в vendor-react (правило
  // id.includes("react") стояло первым и перехватывало их). Между кусками
  // возникали встречные зависимости, и в собранном приложении React
  // оказывался undefined — белый экран с "Cannot read properties of
  // undefined (reading 'useState' / 'createContext')". В dev-режиме этого
  // не видно: там модули не склеиваются.
  //
  // Один общий кусок исключает такие циклы по построению. Точечная разбивка
  // возможна, но требует учёта реального графа зависимостей, а не подстрок.
  return "vendor";
};

export default defineConfig(({ mode }) => {
  const isTest = mode === "test";

  return {
    plugins: [
      react(),
      tsconfigPaths(),
      !isTest &&
        VitePWA({
          registerType: "autoUpdate",
          includeAssets: [
            "pwa-icon.svg",
            "mask-icon.svg",
            "apple-touch-icon.svg",
          ],
          manifest: {
            name: "PRT OT SaaS Platform",
            short_name: "PRT OT",
            description:
              "Tenant-aware operational platform for OT, PB, fire safety, ecology, EDO and document workflows.",
            theme_color: "#0f172a",
            background_color: "#f8fafc",
            display: "standalone",
            start_url: "/",
            scope: "/",
            icons: [
              {
                src: "/pwa-icon.svg",
                sizes: "any",
                type: "image/svg+xml",
                purpose: "any",
              },
              {
                src: "/mask-icon.svg",
                sizes: "any",
                type: "image/svg+xml",
                purpose: "maskable",
              },
              {
                src: "/apple-touch-icon.svg",
                sizes: "180x180",
                type: "image/svg+xml",
                purpose: "any",
              },
            ],
          },
          workbox: {
            navigateFallback: "/index.html",
            cleanupOutdatedCaches: true,
            clientsClaim: true,
            skipWaiting: true,
            globPatterns: ["**/*.{js,css,html,svg,png,ico,json}"],
            runtimeCaching: [
              {
                urlPattern: ({ request }) => request.mode === "navigate",
                handler: "NetworkFirst",
                options: { cacheName: "app-shell" },
              },
              {
                urlPattern: ({ request }) =>
                  ["style", "script", "worker"].includes(request.destination),
                handler: "StaleWhileRevalidate",
                options: { cacheName: "static-assets" },
              },
            ],
          },
          devOptions: {
            enabled: mode === "development",
            navigateFallback: "index.html",
          },
        }),
    ].filter(Boolean),
    server: {
      host: true,
      port: 5173,
      proxy: {
        "/api": {
          target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: mode === "development",
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          manualChunks,
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./vitest.setup.ts",
      css: true,
      api: false,
      exclude: [...configDefaults.exclude, "**/e2e/**"],
      // VitePWA в тестовом режиме отключён — его виртуальный модуль подменяем заглушкой.
      alias: {
        "virtual:pwa-register": fileURLToPath(
          new URL("./src/pwa/pwaRegisterStub.ts", import.meta.url),
        ),
      },
    },
  };
});
