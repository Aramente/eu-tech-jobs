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

// Country-name lookup + city-to-country map. The CITY_TO_COUNTRY table
// resolves jobs whose company.country is XX (aggregator-discovered) or
// missing — we still want them in the right country bucket if the
// location string says "London" or "Berlin". This recovers ~1,500
// previously-unclassifiable jobs.
const COUNTRY_NAMES = {
  FR: "France", DE: "Germany", GB: "United Kingdom", ES: "Spain", IT: "Italy",
  NL: "Netherlands", BE: "Belgium", SE: "Sweden", DK: "Denmark", FI: "Finland",
  NO: "Norway", IE: "Ireland", PT: "Portugal", PL: "Poland", CZ: "Czechia",
  AT: "Austria", CH: "Switzerland", EE: "Estonia", LT: "Lithuania", LV: "Latvia",
  GR: "Greece", RO: "Romania", BG: "Bulgaria", HU: "Hungary", SK: "Slovakia",
  SI: "Slovenia", HR: "Croatia", LU: "Luxembourg", IS: "Iceland", CY: "Cyprus",
  MT: "Malta", US: "United States", CA: "Canada", IL: "Israel", UA: "Ukraine",
  XX: "Remote / unknown",
};
const CITY_TO_COUNTRY = {
  // United Kingdom
  "london": "United Kingdom", "manchester": "United Kingdom",
  "edinburgh": "United Kingdom", "birmingham": "United Kingdom",
  "glasgow": "United Kingdom", "bristol": "United Kingdom",
  "cambridge": "United Kingdom", "leeds": "United Kingdom",
  // Germany
  "berlin": "Germany", "munich": "Germany", "münchen": "Germany",
  "hamburg": "Germany", "frankfurt": "Germany", "köln": "Germany",
  "cologne": "Germany", "düsseldorf": "Germany", "stuttgart": "Germany",
  "leipzig": "Germany", "dresden": "Germany", "nuremberg": "Germany",
  "hannover": "Germany",
  // France
  "paris": "France", "lyon": "France", "marseille": "France",
  "toulouse": "France", "lille": "France", "nice": "France",
  "bordeaux": "France", "strasbourg": "France", "nantes": "France",
  "saint-denis": "France", "rennes": "France",
  // Spain
  "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
  "sevilla": "Spain", "seville": "Spain", "bilbao": "Spain",
  "málaga": "Spain", "malaga": "Spain",
  // Italy
  "rome": "Italy", "roma": "Italy", "milan": "Italy", "milano": "Italy",
  "naples": "Italy", "napoli": "Italy", "turin": "Italy", "torino": "Italy",
  "bologna": "Italy", "florence": "Italy", "firenze": "Italy",
  // Netherlands
  "amsterdam": "Netherlands", "rotterdam": "Netherlands",
  "the hague": "Netherlands", "utrecht": "Netherlands",
  "eindhoven": "Netherlands", "den haag": "Netherlands",
  // Belgium
  "brussels": "Belgium", "bruxelles": "Belgium", "antwerp": "Belgium",
  "antwerpen": "Belgium", "ghent": "Belgium", "gent": "Belgium",
  "liège": "Belgium", "liege": "Belgium",
  // Sweden
  "stockholm": "Sweden", "gothenburg": "Sweden", "göteborg": "Sweden",
  "malmö": "Sweden", "malmo": "Sweden", "lund": "Sweden",
  // Denmark
  "copenhagen": "Denmark", "københavn": "Denmark", "aarhus": "Denmark",
  // Finland
  "helsinki": "Finland", "espoo": "Finland", "tampere": "Finland",
  // Norway
  "oslo": "Norway", "bergen": "Norway", "trondheim": "Norway",
  // Ireland
  "dublin": "Ireland", "cork": "Ireland", "galway": "Ireland",
  // Portugal
  "lisbon": "Portugal", "lisboa": "Portugal", "porto": "Portugal",
  // Poland
  "warsaw": "Poland", "warszawa": "Poland", "kraków": "Poland",
  "krakow": "Poland", "wrocław": "Poland", "wroclaw": "Poland",
  "gdańsk": "Poland", "gdansk": "Poland", "poznań": "Poland",
  // Czechia
  "prague": "Czechia", "praha": "Czechia", "brno": "Czechia",
  // Austria
  "vienna": "Austria", "wien": "Austria", "graz": "Austria",
  // Switzerland
  "zurich": "Switzerland", "zürich": "Switzerland",
  "geneva": "Switzerland", "genève": "Switzerland", "basel": "Switzerland",
  "lausanne": "Switzerland", "bern": "Switzerland",
  // Baltics
  "tallinn": "Estonia", "riga": "Latvia", "vilnius": "Lithuania",
  "kaunas": "Lithuania",
  // Balkans / Eastern Europe
  "athens": "Greece", "thessaloniki": "Greece",
  "bucharest": "Romania", "bucurești": "Romania",
  "sofia": "Bulgaria", "budapest": "Hungary",
  "bratislava": "Slovakia", "ljubljana": "Slovenia", "zagreb": "Croatia",
  "limassol": "Cyprus", "nicosia": "Cyprus",
  // Other
  "luxembourg": "Luxembourg", "reykjavik": "Iceland",
};

function deriveWhere(job, company) {
  // Globally-remote LLM tags win first.
  if (job.remote_policy === "remote-global") return "Remote — Worldwide";
  if (job.remote_policy === "remote-eu") return "Remote — Europe";

  const loc = (job.location || "").toLowerCase();
  if (loc) {
    if (/anywhere in the world|worldwide|world\s*wide|global/.test(loc)) {
      return "Remote — Worldwide";
    }
    if (/\beurope\b|\bemea\b|\beu\b|remote\s*[-—]\s*eu/i.test(loc)) {
      return "Remote — Europe";
    }
    // City lookup
    for (const [city, country] of Object.entries(CITY_TO_COUNTRY)) {
      if (loc.includes(city)) return country;
    }
    // Country names directly in the location string
    for (const [code, name] of Object.entries(COUNTRY_NAMES)) {
      if (loc.includes(name.toLowerCase())) return name;
    }
    // ISO country code suffix (",ee" / ", de" / ", gb")
    const m = loc.match(/,\s*([a-z]{2})\b/);
    if (m && COUNTRY_NAMES[m[1].toUpperCase()]) {
      return COUNTRY_NAMES[m[1].toUpperCase()];
    }
  }

  // Fall back to company HQ — but only for EU countries. A job at a US-HQ
  // company with location "Hybrid" / "Remote" / "NAMER" should not be
  // stamped "United States" — that polluted the EU-only board with
  // 1,634 ghost-US jobs. Those land in "Other" instead.
  const EU_HQ_COUNTRIES = new Set([
    "FR", "DE", "GB", "ES", "IT", "NL", "BE", "SE", "DK", "FI", "NO",
    "IE", "PT", "PL", "CZ", "AT", "CH", "EE", "LT", "LV", "GR", "RO",
    "BG", "HU", "SK", "SI", "HR", "LU", "IS", "CY", "MT", "UA",
  ]);
  if (company?.country && EU_HQ_COUNTRIES.has(company.country)) {
    return COUNTRY_NAMES[company.country];
  }
  if (job.remote_policy === "remote") return "Remote — unspecified";
  return "Other";
}

const facetCounts = { role: {}, country: {}, source: {}, where: {} };
const whereByJobId = {};
for (const j of jobs) {
  if (j.role_family) facetCounts.role[j.role_family] = (facetCounts.role[j.role_family] || 0) + 1;
  if (j.source) facetCounts.source[j.source] = (facetCounts.source[j.source] || 0) + 1;
  const c = companiesByslug[j.company_slug];
  if (c?.country) {
    facetCounts.country[c.country] = (facetCounts.country[c.country] || 0) + 1;
  }
  const where = deriveWhere(j, c);
  whereByJobId[j.id] = where;
  facetCounts.where[where] = (facetCounts.where[where] || 0) + 1;
}
writeFileSync(join(OUT_DIR, "facet-counts.json"), JSON.stringify(facetCounts));
// Per-job derived `where` lookup so the per-job page can use the same
// classification (matches the home-page facet counts).
writeFileSync(join(OUT_DIR, "where-by-id.json"), JSON.stringify(whereByJobId));

const feedSrc = join(DATA, "feed.xml");
if (existsSync(feedSrc)) {
  copyFileSync(feedSrc, join(PUBLIC_DIR, "feed.xml"));
}

console.log(
  `[parquet-to-json] ${jobsLite.length} jobs, ${companies.length} companies, ` +
    `${descCount} per-job .md files → src/data/ + data-cache/descriptions/`
);
