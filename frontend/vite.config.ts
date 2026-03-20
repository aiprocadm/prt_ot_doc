import { defineConfig, type UserConfig } from "vite";
import react from "@vitejs/plugin-react";
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
  plugins: [react(), tsconfigPaths()],
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
  },
}));
