import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/posts": {
        target: "http://127.0.0.1:8000",
        bypass(req) {
          if (req.url?.startsWith("/posts/workspace")) return req.url;
          return undefined;
        },
      },
      "/schedules": "http://127.0.0.1:8000",
      "/sources": "http://127.0.0.1:8000",
    },
  },
});
