import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiRoutes = ["/health", "/customers", "/knowledge", "/rfps", "/proposals"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: Object.fromEntries(
      apiRoutes.map((route) => [route, { target: "http://localhost:8000", changeOrigin: true }]),
    ),
  },
});
