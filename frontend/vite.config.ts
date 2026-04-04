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

  if (id.includes("react") || id.includes("scheduler")) {
    return "vendor-react";
  }
  if (id.includes("@tanstack") || id.includes("zustand") || id.includes("immer")) {
    return "vendor-state";
  }
  if (id.includes("@radix-ui") || id.includes("lucide-react") || id.includes("sonner")) {
    return "vendor-ui";
  }
  if (id.includes("react-hook-form") || id.includes("@hookform") || id.includes("zod")) {
    return "vendor-forms";
  }
  if (id.includes("i18next") || id.includes("react-i18next") || id.includes("date-fns")) {
    return "vendor-i18n";
  }
  if (id.includes("axios")) {
    return "vendor-network";
  }

  return "vendor-misc";
};

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tsconfigPaths(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["pwa-icon.svg", "mask-icon.svg", "apple-touch-icon.svg"],
      manifest: {
        name: "PRT OT SaaS Platform",
        short_name: "PRT OT",
        description: "Tenant-aware operational platform for OT, PB, fire safety, ecology, EDO and document workflows.",
        theme_color: "#0f172a",
        background_color: "#f8fafc",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/pwa-icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
          { src: "/mask-icon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
          { src: "/apple-touch-icon.svg", sizes: "180x180", type: "image/svg+xml", purpose: "any" }
        ]
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
            options: { cacheName: "app-shell" }
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/pwa/sync"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-read-models",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 80, maxAgeSeconds: 60 * 10 },
              cacheableResponse: { statuses: [0, 200] }
            }
          },
          {
            urlPattern: ({ request }) => ["style", "script", "worker"].includes(request.destination),
            handler: "StaleWhileRevalidate",
            options: { cacheName: "static-assets" }
          }
        ]
      },
      devOptions: {
        enabled: mode === "development",
        navigateFallback: "index.html"
      }
    })
  ],
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
    exclude: [...configDefaults.exclude, "**/e2e/**"],
  },
}));
