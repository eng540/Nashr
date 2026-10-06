import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/posts": "http://127.0.0.1:8000",
      "/schedules": "http://127.0.0.1:8000",
      "/sources": "http://127.0.0.1:8000",
    },
  },
});
