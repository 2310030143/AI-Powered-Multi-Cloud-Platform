import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // listen on 0.0.0.0 so the app works inside dev containers/proxies
    // Local dev only. The production artifact is a static build (no server).
    allowedHosts: [".e2b.app"],
    // Dev proxy: the browser only ever talks to the Vite origin; /api calls
    // are forwarded to the local FastAPI backend (avoids CORS in development).
    // VITE_API_BASE_URL can override this with an absolute URL if desired.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: false,
  },
});
