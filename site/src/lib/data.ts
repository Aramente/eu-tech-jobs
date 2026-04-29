import jobsRaw from "../data/jobs.json";
import companiesRaw from "../data/companies.json";
import metaRaw from "../data/metadata.json";

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
  description_md: string;
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
