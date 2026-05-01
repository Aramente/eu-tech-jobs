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
// Classify employment type from the title. Rule order: internship > apprenticeship
// > freelance > permanent (default). "Contract" alone is too noisy to count
// as freelance — many full-time roles use the word generically.
const INT_RE = /\b(intern|interns|internship|stagiaire|stagiaires|stagista|trainee|trainees|praktikum|praktikant|praktikantin)\b/i;
const ALT_RE = /\b(alternan(?:t|ts|ce|te|tes)|apprentic(?:e|es|eship)|ausbildung|werkstudent|werkstudentin|lehre|lehrling|apprenti|apprentie)\b/i;
const FREE_RE = /\b(freelance|freelancer|freelancers|freelancing|contractor|contractors)\b/i;
function employmentType(title) {
  if (!title) return "permanent";
  if (INT_RE.test(title)) return "internship";
  if (ALT_RE.test(title)) return "apprenticeship";
  if (FREE_RE.test(title)) return "freelance";
  return "permanent";
}

// Derive role_family from title when the upstream LLM tagger didn't tag the
// job. Currently only ~8% of the dataset has role_family — this regex
// fallback recovers coarse classification for the rest. Order matters:
// more specific rules go first (ml-ai before engineering, hr before ops).
const ROLE_RULES = [
  ["hr",          /\b(recruit(er|ers|ing|ment)?|talent\s*acquisition|talent\s*partner|talent\s*lead|people\s*partner|people\s*ops|people\s*operations|hr\s*business|hrbp|head\s*of\s*hr|hr\s*manager|hr\s*coordinator|head\s*of\s*people|chief\s*people|head\s*of\s*talent|chro)\b/i],
  ["ml-ai",       /\b(machine\s*learning|ml\s*engineer|ml\s*ops|mlops|ai\s*engineer|ai\s*scientist|llm|nlp|computer\s*vision|deep\s*learning|applied\s*ai|generative\s*ai|gen\s*ai|prompt\s*engineer)\b/i],
  ["data",        /\b(data\s*analyst|data\s*engineer|data\s*scientist|analytics\s*engineer|analytics\s*manager|business\s*intelligence|\bbi\s*(developer|engineer|analyst))\b/i],
  ["product",     /\b(product\s*manager|product\s*owner|product\s*lead|product\s*marketing|head\s*of\s*product|chief\s*product|cpo|associate\s*product|technical\s*product)\b/i],
  ["design",      /\b(designer|design\s*lead|ux\b|ui\b|user\s*experience|user\s*interface|visual\s*design|brand\s*design|product\s*design|graphic\s*design|ux\/ui)\b/i],
  ["marketing",   /\b(marketing|growth\s*(manager|lead|hacker)|seo\s*(manager|specialist)?|sem|content\s*(manager|writer|strategist)|community\s*manager|brand\s*(manager|lead)|demand\s*generation|digital\s*marketing|social\s*media\s*(manager|lead)|marketing\s*manager|cmo)\b/i],
  ["sales",       /\b(sales|account\s*executive|\bae\b|sdr|bdr|account\s*manager|business\s*development|customer\s*success|partnerships?\s*manager|key\s*account|inside\s*sales|outside\s*sales|territory\s*manager|sales\s*development)\b/i],
  ["finance",     /\b(finance|accounting|accountant|controller|fp&a|treasurer|tax\s*(manager|specialist)?|audit\s*(manager|specialist)?|cfo|head\s*of\s*finance|payroll\s*specialist)\b/i],
  ["legal",       /\b(legal\s*counsel|general\s*counsel|legal\s*manager|compliance\s*(officer|manager)|privacy\s*(officer|counsel)|regulatory|paralegal|gdpr)\b/i],
  ["support",     /\b(customer\s*service|customer\s*support|technical\s*support|helpdesk|help\s*desk|onboarding\s*specialist|support\s*engineer|support\s*specialist|customer\s*operations)\b/i],
  ["research",    /\b(research\s*scientist|research\s*engineer|research\s*lead|principal\s*researcher|phd\s*scientist|scientific\s*officer)\b/i],
  ["engineering", /\b(engineer|engineering|developer|swe\b|software|backend|frontend|front-end|back-end|fullstack|full-stack|full\s*stack|devops|sre\b|site\s*reliability|platform\s*engineer|qa\s*engineer|security\s*engineer|architect|tech\s*lead|cto)\b/i],
  ["ops",         /\b(operations|\bops\b|coordinator|administrator|project\s*manager|program\s*manager|pmo|chief\s*of\s*staff|business\s*operations|revenue\s*operations|revops)\b/i],
];
function inferRole(title) {
  if (!title) return null;
  for (const [name, re] of ROLE_RULES) {
    if (re.test(title)) return name;
  }
  return null;
}

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
  role_family: j.role_family || inferRole(j.title),
  employment_type: employmentType(j.title),
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
    // City lookup — token-based so "Venice, Italy" doesn't substring-match
    // "nice" (France). Tokenize on punctuation/whitespace, then match each
    // city as a standalone token.
    const tokens = loc.split(/[^a-zàâäéèêëïîôöùûüçœæñ\-]+/u).filter(Boolean);
    const tokenSet = new Set(tokens);
    for (const [city, country] of Object.entries(CITY_TO_COUNTRY)) {
      if (tokenSet.has(city)) return country;
    }
    // Country names — same token-based check. Multi-word names checked as
    // a substring of the original loc since they include spaces.
    for (const [code, name] of Object.entries(COUNTRY_NAMES)) {
      const lower = name.toLowerCase();
      if (lower.includes(" ")) {
        if (loc.includes(lower)) return name;
      } else if (tokenSet.has(lower)) {
        return name;
      }
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
