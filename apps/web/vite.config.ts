import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiPort = process.env.STT_API_PORT || "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.STT_WEB_PORT || 5173),
    strictPort: true,
    proxy: { "/api": `http://127.0.0.1:${apiPort}` },
  },
});
