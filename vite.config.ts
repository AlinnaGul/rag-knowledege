import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => {
  const isDev = mode === "development";

  return {
    server: {
      host: "0.0.0.0",     // IPv4 (Windows/LAN friendly)
      port: 8080,
      strictPort: true,
      proxy: isDev
        ? {
            "/api": {
              target: "http://127.0.0.1:8000",
              changeOrigin: true,
              secure: false,
            },
          }
        : undefined,
    },
    preview: { host: "0.0.0.0", port: 8080, strictPort: true },
    plugins: [react(), isDev && componentTagger()].filter(Boolean),
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
  };
});
