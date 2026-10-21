import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Temporary config for the visual regression check only.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5176,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8015", changeOrigin: true },
    },
  },
});
