import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://aramente.github.io",
  base: "/ai-startups",
  trailingSlash: "ignore",
  build: {
    assets: "_assets",
  },
});
