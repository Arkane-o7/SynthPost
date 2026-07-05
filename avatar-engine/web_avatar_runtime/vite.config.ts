import { defineConfig } from "vite";
import { fileURLToPath } from "url";
import path from "path";

// ESM-safe __dirname equivalent
const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // root stays as web_avatar_runtime/ (Vite default when run from this dir).
  // The Python HTTP server serves desk-avatar-engine/ so asset URLs like
  // /assets/avatars/... resolve against the project root.  The browser runtime
  // fetches those URLs from the same host:port as the page itself.
  base: "./",

  build: {
    // Outputs to web_avatar_runtime/dist/ — served at /web_avatar_runtime/dist/
    outDir: path.resolve(__dirname, "dist"),
    emptyOutDir: true,
  },

  server: {
    // Allow the dev server to serve files from the project root so that
    // /assets/ and /episodes/ paths in job JSON resolve correctly.
    fs: {
      allow: [__dirname, path.resolve(__dirname, "..")],
    },
  },

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
