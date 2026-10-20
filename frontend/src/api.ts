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
  first_seen_at: string;
  bookmarked: boolean;
  hidden: boolean;
  breakdown: Breakdown | null;
}

export interface Breakdown {
  skills: number;
  domain: number;
  seniority: number;
  preferred: number;
}

export interface Feedback {
  items: string[];
  created_at: string;
  current: boolean;
}

export interface PostingDetail extends Posting {
  description: string | null;
  requirements: string[] | null;
  preferred: string[] | null;
  feedback: Feedback | null;
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

export type Provider = "claude" | "codex";

export interface ProviderSetting {
  provider: Provider;
  chosen: boolean;
}

export interface AuthStatus {
  provider: Provider;
  logged_in: boolean;
  login_command: string;
}

/** 스크래핑·피드백 401. body가 있으면 provider·message를 담는다 */
export class LoginRequiredError extends Error {
  provider: Provider | null;
  constructor(body?: { provider?: Provider; message?: string } | null) {
    super(body?.message ?? "로그인이 필요합니다. 터미널에서 로그인 후 다시 시도해주세요.");
    this.provider = body?.provider ?? null;
  }
}

/** job 실행 중이라 provider 변경·스크래핑 시작 불가 (409) */
export class JobRunningError extends Error {}

/** 공고 상세·피드백 404 (없음·삭제) */
export class NotFoundError extends Error {}

/** 피드백 생성 502·400. message는 서버 message */
export class LlmError extends Error {}

/** 이력서 업로드 400. message는 서버 detail (확장자·텍스트 없는 PDF 등) */
export class ResumeRejectedError extends Error {}

const readJson = (r: Response) => r.json().catch(() => null);

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
  authStatus: () => get<AuthStatus>("/api/auth/status"),
  providerSetting: () => get<ProviderSetting>("/api/settings/provider"),
  async setProvider(provider: Provider): Promise<AuthStatus> {
    const r = await fetch("/api/settings/provider", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }) });
    if (r.status === 409) throw new JobRunningError((await readJson(r))?.message ?? "job running");
    if (!r.ok) throw new Error(`provider: ${r.status}`);
    return r.json();
  },
  companies: () => get<Company[]>("/api/companies"),
  postings: () => get<Posting[]>("/api/postings"),
  async posting(id: number): Promise<PostingDetail> {
    const r = await fetch(`/api/postings/${id}`);
    if (r.status === 404) throw new NotFoundError("posting not found");
    if (!r.ok) throw new Error(`posting: ${r.status}`);
    return r.json();
  },
  async generateFeedback(id: number): Promise<{ posting_id: number; feedback: Feedback }> {
    const r = await fetch(`/api/postings/${id}/feedback`, { method: "POST" });
    if (r.ok) return r.json();
    if (r.status === 404) throw new NotFoundError("posting not found");
    if (r.status === 401) throw new LoginRequiredError(await readJson(r));
    if (r.status === 409) throw new JobRunningError((await readJson(r))?.message ?? "job running");
    if (r.status === 400 || r.status === 502) throw new LlmError((await readJson(r))?.message ?? `feedback: ${r.status}`);
    throw new Error(`feedback: ${r.status}`);
  },
  job: (id: string) => get<Job>(`/api/scrape/${id}`),
  resumeFiles: () => get<ResumeFile[]>("/api/resume"),
  async putResume(name: string, file: Blob): Promise<void> {
    const r = await fetch(`/api/resume/${encodeURIComponent(name)}`, { method: "PUT", headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (r.ok) return;
    const detail = (await readJson(r))?.detail;
    const message = typeof detail === "string" ? detail : `resume: ${r.status}`;
    throw r.status === 400 ? new ResumeRejectedError(message) : new Error(message);
  },
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
    if (r.status === 401) throw new LoginRequiredError(await readJson(r));
    if (r.status === 409) throw new JobRunningError((await readJson(r))?.message ?? "job running");
    if (!r.ok) throw new Error(`scrape: ${r.status}`);
    return r.json();
  },
};
