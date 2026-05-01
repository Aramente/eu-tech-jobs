import { defineConfig } from "astro/config";

// Custom domain: eu-tech.jobs (CNAME file at site/public/CNAME).
// Once DNS is wired (A records → GitHub Pages IPs + AAAA optionally) and
// GitHub Pages confirms the TLS cert, the site serves at https://eu-tech.jobs/
// instead of the previous /eu-tech-jobs/ subpath.
export default defineConfig({
  site: "https://eu-tech.jobs",
  base: "/",
  trailingSlash: "ignore",
  build: {
    assets: "_assets",
  },
});
