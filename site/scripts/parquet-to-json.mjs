// Pre-build hook: read data/latest/jobs.parquet → emit src/data/jobs.json.
// Keeps the Astro pipeline pure JS without bundling pyarrow.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parquetReadObjects } from "hyparquet";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");

const JOBS = join(ROOT, "data", "latest", "jobs.parquet");
const COMPANIES = join(ROOT, "data", "latest", "companies.parquet");
const META = join(ROOT, "data", "latest", "metadata.json");
const OUT_DIR = join(__dirname, "..", "src", "data");
mkdirSync(OUT_DIR, { recursive: true });

async function loadParquet(path) {
  if (!existsSync(path)) {
    console.warn(`[parquet-to-json] Missing ${path} — emitting empty array.`);
    return [];
  }
  const buf = readFileSync(path);
  const file = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return await parquetReadObjects({ file });
}

const jobs = await loadParquet(JOBS);
const companies = await loadParquet(COMPANIES);

// Trim heavy fields not needed in the index page.
const jobsLite = jobs.map((j) => ({
  id: j.id,
  company_slug: j.company_slug,
  title: j.title,
  url: j.url,
  location: j.location,
  source: j.source,
  posted_at: j.posted_at ? new Date(Number(j.posted_at) * 1000).toISOString() : null,
}));

const companiesByslug = Object.fromEntries(companies.map((c) => [c.slug, c]));

const meta = existsSync(META) ? JSON.parse(readFileSync(META, "utf8")) : {};

writeFileSync(join(OUT_DIR, "jobs.json"), JSON.stringify(jobsLite));
writeFileSync(join(OUT_DIR, "companies.json"), JSON.stringify(companiesByslug));
writeFileSync(join(OUT_DIR, "metadata.json"), JSON.stringify(meta));

console.log(
  `[parquet-to-json] ${jobsLite.length} jobs, ${companies.length} companies → src/data/`
);
