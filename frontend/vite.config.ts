import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const TOKEN_FILE_PATH = path.resolve(__dirname, "../backend/.local_token");

function readBackendToken(): string {
  try {
    if (fs.existsSync(TOKEN_FILE_PATH)) {
      return fs.readFileSync(TOKEN_FILE_PATH, "utf-8").trim();
    }
  } catch {
    // Caso o backend ainda não tenha sido iniciado na primeira vez
  }
  return "";
}

/**
 * Plugin Vite para injetar dinamicamente o token local do backend no HTML durante o modo dev,
 * espelhando exatamente o comportamento de injeção que o FastAPI fará em produção (Task 16).
 */
function injectLocalTokenPlugin(): Plugin {
  return {
    name: "x-assistant-inject-local-token",
    transformIndexHtml(html) {
      const currentToken = readBackendToken();
      const scriptTag = `<script>window.__X_LOCAL_TOKEN__ = ${JSON.stringify(currentToken)};</script>`;
      return html.replace("</head>", `  ${scriptTag}\n  </head>`);
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), injectLocalTokenPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    __DEV_LOCAL_TOKEN__: JSON.stringify(readBackendToken()),
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-icons": ["lucide-react", "sonner"],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
});

