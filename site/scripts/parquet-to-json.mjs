// Pre-build hook: read data/latest/{jobs,companies}.parquet → emit JSON for Astro.

import { readFileSync, writeFileSync, existsSync, mkdirSync, copyFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parquetReadObjects } from "hyparquet";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");
const DATA = join(ROOT, "data");
const OUT_DIR = join(__dirname, "..", "src", "data");
const PUBLIC_DIR = join(__dirname, "..", "public");
mkdirSync(OUT_DIR, { recursive: true });
mkdirSync(PUBLIC_DIR, { recursive: true });

async function loadParquet(path) {
  if (!existsSync(path)) {
    console.warn(`[parquet-to-json] Missing ${path} — emitting empty.`);
    return [];
  }
  const buf = readFileSync(path);
  const file = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return await parquetReadObjects({ file });
}

const jobs = await loadParquet(join(DATA, "latest", "jobs.parquet"));
const companies = await loadParquet(join(DATA, "latest", "companies.parquet"));

function isoDate(v) {
  if (v == null) return null;
  if (typeof v === "string") return v;
  const n = typeof v === "bigint" ? Number(v) : v;
  return new Date(n * 1000).toISOString();
}

// description_md is intentionally omitted from the lite payload — at scale
// (~15k jobs × multi-KB descriptions) the JSON.stringify call OOMs Node.
// Instead each job's description is written to its own .md file in
// `data-cache/descriptions/` and the per-job Astro page reads only its
// own file at build time. ~15k tiny disk reads, no big JSON ever exists.
const jobsLite = jobs.map((j) => ({
  id: j.id,
  company_slug: j.company_slug,
  title: j.title,
  url: j.url,
  location: j.location,
  source: j.source,
  posted_at: isoDate(j.posted_at),
  remote_policy: j.remote_policy,
  seniority: j.seniority,
  role_family: j.role_family,
  has_description: !!(j.description_md && j.description_md.length > 50),
}));

// Per-job description files. Path is intentionally outside `src/` so Vite
// doesn't try to watch / bundle 15k files.
const DESC_DIR = join(__dirname, "..", "data-cache", "descriptions");
mkdirSync(DESC_DIR, { recursive: true });
let descCount = 0;
for (const j of jobs) {
  if (j.description_md && j.description_md.length > 0) {
    writeFileSync(join(DESC_DIR, `${j.id}.md`), j.description_md);
    descCount++;
  }
}

const companiesByslug = Object.fromEntries(companies.map((c) => [c.slug, c]));

const metaPath = join(DATA, "latest", "metadata.json");
const meta = existsSync(metaPath) ? JSON.parse(readFileSync(metaPath, "utf8")) : {};

writeFileSync(join(OUT_DIR, "jobs.json"), JSON.stringify(jobsLite));
writeFileSync(join(OUT_DIR, "companies.json"), JSON.stringify(companiesByslug));
writeFileSync(join(OUT_DIR, "metadata.json"), JSON.stringify(meta));

const feedSrc = join(DATA, "feed.xml");
if (existsSync(feedSrc)) {
  copyFileSync(feedSrc, join(PUBLIC_DIR, "feed.xml"));
}

console.log(
  `[parquet-to-json] ${jobsLite.length} jobs, ${companies.length} companies, ` +
    `${descCount} per-job .md files → src/data/ + data-cache/descriptions/`
);
