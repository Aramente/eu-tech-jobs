import jobsRaw from "../data/jobs.json";
import companiesRaw from "../data/companies.json";
import metaRaw from "../data/metadata.json";
import facetCountsRaw from "../data/facet-counts.json";

export type Job = {
  id: string;
  company_slug: string;
  title: string;
  url: string;
  location: string;
  source: string;
  posted_at: string | null;
  remote_policy: string | null;
  seniority: string | null;
  role_family: string | null;
  has_description?: boolean;
};

export type Company = {
  slug: string;
  name: string;
  country: string;
  categories: string[];
  ats_provider?: string;
  ats_handle?: string;
  career_url?: string;
  github_org?: string;
  funding_stage?: string;
  size_bucket?: string;
  notes?: string;
};

export const jobs = jobsRaw as Job[];
export const companies = companiesRaw as Record<string, Company>;
export const meta = metaRaw as {
  run_at?: string;
  job_count?: number;
  company_count?: number;
  extractor_results?: Array<{ success: boolean }>;
};
export const facetCounts = facetCountsRaw as {
  role: Record<string, number>;
  country: Record<string, number>;
  source: Record<string, number>;
  where: Record<string, number>;
};

export function jobSlug(j: Job) {
  return j.id;
}

export function jobsSorted(): Job[] {
  return [...jobs].sort((a, b) => {
    if (a.posted_at && b.posted_at) return b.posted_at.localeCompare(a.posted_at);
    if (a.posted_at) return -1;
    if (b.posted_at) return 1;
    return a.company_slug.localeCompare(b.company_slug);
  });
}

export function jobsByCompany(): Record<string, Job[]> {
  const byCompany: Record<string, Job[]> = {};
  for (const j of jobs) {
    (byCompany[j.company_slug] ||= []).push(j);
  }
  return byCompany;
}

export const PAGE_SIZE = 100;
/** Cap any single company at this many jobs on page 1 only — keeps mass
 *  hirers (Delivery Hero / Databricks etc) from eating the whole front
 *  page. Spillover lives on later pages in pure recency order. */
export const PAGE_1_PER_COMPANY_CAP = 5;

/**
 * The page-1 set: top jobs by posted_at desc, capped at
 * PAGE_1_PER_COMPANY_CAP per company. Improves company diversity on the
 * landing page from ~5–8 companies to ~30+.
 */
export function jobsForFrontPage(): Job[] {
  const sorted = jobsSorted();
  const perCompany: Record<string, number> = {};
  const front: Job[] = [];
  const overflow: Job[] = [];
  for (const j of sorted) {
    const n = perCompany[j.company_slug] || 0;
    if (n < PAGE_1_PER_COMPANY_CAP && front.length < PAGE_SIZE) {
      front.push(j);
      perCompany[j.company_slug] = n + 1;
    } else {
      overflow.push(j);
    }
    if (front.length >= PAGE_SIZE) break;
  }
  return front;
}

/** Format an ISO date string (YYYY-MM-DD or full ISO) as DD/MM/YYYY (European). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ymd = iso.slice(0, 10);
  const [y, m, d] = ymd.split("-");
  if (!y || !m || !d) return "—";
  return `${d}/${m}/${y}`;
}

/**
 * Display the company's country.
 * "XX" is the placeholder we assign to aggregator-discovered companies whose
 * country couldn't be inferred — show that as "Remote" since they all came
 * from remote-friendly aggregators (RemoteOK, WeWorkRemotely, JustJoin.it).
 */
export function displayCountry(code: string | null | undefined): string {
  if (!code) return "—";
  if (code === "XX") return "Remote";
  return code;
}

/** Full country names — used in dropdowns and Pagefind filter values. */
export const COUNTRY_NAMES: Record<string, string> = {
  FR: "France", DE: "Germany", GB: "United Kingdom", ES: "Spain", IT: "Italy",
  NL: "Netherlands", BE: "Belgium", SE: "Sweden", DK: "Denmark", FI: "Finland",
  NO: "Norway", IE: "Ireland", PT: "Portugal", PL: "Poland", CZ: "Czechia",
  AT: "Austria", CH: "Switzerland", EE: "Estonia", LT: "Lithuania", LV: "Latvia",
  GR: "Greece", RO: "Romania", BG: "Bulgaria", HU: "Hungary", SK: "Slovakia",
  SI: "Slovenia", HR: "Croatia", LU: "Luxembourg", IS: "Iceland", CY: "Cyprus",
  MT: "Malta", US: "United States", CA: "Canada", IL: "Israel", UA: "Ukraine",
  XX: "Remote / unknown",
};

export function countryName(code: string | null | undefined): string {
  if (!code) return "—";
  return COUNTRY_NAMES[code] || code;
}

/** True for aggregator-discovered companies (synthetic stubs). */
export function isAggregatorCompany(slug: string): boolean {
  return slug.startsWith("via-");
}

/** Build a Bored CV deep-link that pre-fills the offer URL. */
export function boredCvLink(jobUrl: string): string {
  return `https://aramente.github.io/bored-cv/upload?offer_url=${encodeURIComponent(jobUrl)}`;
}

/** Slugify a string: ASCII-fold, alnum + hyphens, capped length. */
function slugify(s: string): string {
  return (s || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // strip diacritics
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/g, ""); // trim trailing dash if cut mid-word
}

/**
 * Per-job page path *relative to the site base*, in the form
 * `<company-slug>/<title-slug>-<id8>`. The 8-char hash suffix preserves
 * stability across daily snapshots (same posting → same URL even if the
 * title is reworded slightly), while the readable prefix gives SEO and
 * shareability over the previous opaque-hash scheme.
 */
export function jobUrlPath(job: Job): string {
  const title = slugify(job.title) || "job";
  const idShort = job.id.slice(0, 8);
  return `${job.company_slug}/${title}-${idShort}`;
}
