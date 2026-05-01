import { defineConfig } from "astro/config";

// CURRENT: site is served at https://aramente.github.io/eu-tech-jobs/
// (GitHub Pages subpath). The CNAME at site/public/CNAME is dormant
// until DNS is wired for eu-tech.jobs.
//
// SWITCH TO CUSTOM DOMAIN: once eu-tech.jobs DNS resolves to GitHub
// Pages and the cert is provisioned, change to:
//   site: "https://eu-tech.jobs",
//   base: "/",
// The CNAME file already tells GitHub which domain to bind.
export default defineConfig({
  site: "https://aramente.github.io",
  base: "/eu-tech-jobs",
  trailingSlash: "ignore",
  build: {
    assets: "_assets",
  },
});
