export type Level = "strong" | "good" | "stretch";
export const LEVEL_RANK: Record<Level, number> = { stretch: 1, good: 2, strong: 3 };

export interface Posting {
  id: number;
  company: string;
  external_id: string;
  title: string;
  summary: string;
  tech_stack: string[];
  fit_level: Level;
  score: number;
  gaps: string[];
  fit_reason: string;
  apply_url: string;
  deadline: string | null;
  category: string | null;
  scraped_at: string;
  bookmarked: boolean;
  hidden: boolean;
}

export interface ScrapeRun {
  status: "running" | "done" | "failed" | "auth_required";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  fetched_count: number | null;
}

export interface Company {
  company: string;
  display_name: string;
  careers_url: string;
  last_run: ScrapeRun | null;
  interested: boolean;
}

export interface ResumeFile {
  name: string;
  size: number;
  updated_at: string;
}

export type CompanyStatus = "pending" | "running" | "done" | "failed" | "auth_required";

export interface Job {
  job_id: string;
  status: "running" | "done" | "auth_required";
  started_at: string;
  finished_at: string | null;
  cost_usd: number;
  companies: Record<string, { status: CompanyStatus; fetched: number; new: number; stored: number; excluded: number; deleted: number; error: string | null }>;
}

export class LoginRequiredError extends Error {}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function send(label: string, path: string, method: string, body?: unknown): Promise<void> {
  const r = await fetch(path, body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${label}: ${r.status}`);
}

export const api = {
  authStatus: () => get<{ logged_in: boolean }>("/api/auth/status"),
  companies: () => get<Company[]>("/api/companies"),
  postings: () => get<Posting[]>("/api/postings"),
  job: (id: string) => get<Job>(`/api/scrape/${id}`),
  resumeFiles: () => get<ResumeFile[]>("/api/resume"),
  putResume: (name: string, content: string) => send("resume", `/api/resume/${encodeURIComponent(name)}`, "PUT", { content }),
  deleteResume: (name: string) => send("resume", `/api/resume/${encodeURIComponent(name)}`, "DELETE"),
  setInterests: (companies: string[]) => send("interests", "/api/interests", "PUT", { companies }),
  setInterest: (company: string, on: boolean) => send("interest", `/api/companies/${company}/interest`, on ? "PUT" : "DELETE"),
  async setBookmark(id: number, on: boolean): Promise<void> {
    const r = await fetch(`/api/postings/${id}/bookmark`, { method: on ? "PUT" : "DELETE" });
    if (!r.ok) throw new Error(`bookmark: ${r.status}`);
  },
  async setHidden(id: number, on: boolean): Promise<void> {
    const r = await fetch(`/api/postings/${id}/hide`, { method: on ? "PUT" : "DELETE" });
    if (!r.ok) throw new Error(`hide: ${r.status}`);
  },
  async startScrape(): Promise<{ job_id: string }> {
    const r = await fetch("/api/scrape", { method: "POST" });
    if (r.status === 401) throw new LoginRequiredError();
    if (!r.ok) throw new Error(`scrape: ${r.status}`);
    return r.json();
  },
};
