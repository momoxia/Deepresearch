import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiPort = env.VITE_API_PORT || "8808";
  const devPort = Number(env.VITE_DEV_PORT || "3020");
  const previewPort = Number(env.VITE_PREVIEW_PORT || "3021");
  const apiTarget = `http://127.0.0.1:${apiPort}`;

  return {
    plugins: [react(), basicSsl()],
    server: {
      host: true,
      port: devPort,
      strictPort: false,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
      },
    },
    preview: {
      host: true,
      port: previewPort,
      strictPort: false,
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
      },
    },
  };
});
