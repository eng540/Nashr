import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/posts": {\n        target: "http://127.0.0.1:8000",\n        bypass(req) {\n          if (req.url?.startsWith("/posts/workspace")) return req.url;\n          return undefined;\n        },\n      },
      "/schedules": "http://127.0.0.1:8000",
      "/sources": "http://127.0.0.1:8000",
    },
  },
});
