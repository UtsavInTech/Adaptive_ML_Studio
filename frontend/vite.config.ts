import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the UI runs on 5173 and the API (including the SSE stream) is proxied to the backend,
// so the browser sees one origin and no CORS configuration is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
