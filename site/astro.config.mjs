import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://aramente.github.io",
  base: "/eu-tech-jobs",
  trailingSlash: "ignore",
  build: {
    assets: "_assets",
  },
});
