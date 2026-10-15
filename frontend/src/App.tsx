import { useCallback, useEffect, useRef, useState } from "react";
import { api, Company, Job, LoginRequiredError, Posting, ResumeFile } from "./api";
import { Logo } from "./components/Logo";
import { PostingsTab } from "./components/PostingsTab";
import { BookmarksTab } from "./components/BookmarksTab";
import { HiddenTab } from "./components/HiddenTab";
import { CompaniesTab } from "./components/CompaniesTab";
import { ScrollTopButton } from "./components/ScrollTopButton";
import { CompanySelect } from "./components/CompanySelect";
import { invalidResumeFiles, ResumeDropzone } from "./components/ResumeDropzone";
import { Toast, ToastMessage } from "./components/Toast";

type Tab = "postings" | "bookmarks" | "hidden" | "companies";

const TAB_LABEL: Record<Tab, string> = { postings: "공고", bookmarks: "북마크", hidden: "숨김", companies: "회사" };

// 낙관적 업데이트로 토글하는 공고 플래그와 그 저장 API
const FLAG_API = { bookmarked: api.setBookmark, hidden: api.setHidden } satisfies Record<string, (id: number, on: boolean) => Promise<void>>;
type Flag = keyof typeof FLAG_API;

export default function App() {
  const [tab, setTab] = useState<Tab>("postings");
  const [postings, setPostings] = useState<Posting[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [loginRequired, setLoginRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeFiles, setResumeFiles] = useState<ResumeFile[] | null>(null);
  const [toast, setToast] = useState<(ToastMessage & { after?: () => void }) | null>(null);
  // 온보딩 업로드 직후 toast가 닫힐 때까지 업로드 화면에 머문다
  const [holdUpload, setHoldUpload] = useState(false);
  const pending = useRef(new Set<string>());
  const toastSeq = useRef(0);

  const reload = useCallback(async () => {
    try {
      const [p, c, r] = await Promise.all([api.postings(), api.companies(), api.resumeFiles()]);
      setPostings(p);
      setCompanies(c);
      setResumeFiles(r);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  // 이전 toast의 after는 새 toast가 닫힐 때 이어서 실행한다
  const showToast = (text: string, kind: ToastMessage["kind"], after?: () => void) =>
    setToast((prev) => {
      const chained = prev?.after && after ? () => (prev.after!(), after()) : (after ?? prev?.after);
      return { id: ++toastSeq.current, text, kind, after: chained };
    });
  const closeToast = () => {
    toast?.after?.();
    setToast(null);
  };

  const uploadResumes = async (files: File[]): Promise<boolean> => {
    const invalid = invalidResumeFiles(files);
    if (invalid) {
      showToast(invalid, "error");
      return false;
    }
    try {
      for (const f of files) await api.putResume(f.name, await f.text());
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      try {
        setResumeFiles(await api.resumeFiles());
      } catch (e) {
        setError(String(e));
      }
    }
  };

  const onboardingUpload = async (files: File[]) => {
    if (!(await uploadResumes(files))) return;
    setHoldUpload(true);
    showToast("이력서를 업로드했습니다", "ok", () => setHoldUpload(false));
  };

  const saveInterests = async (selected: string[]) => {
    try {
      await api.setInterests(selected);
      setCompanies(await api.companies());
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    reload();
  }, [reload]);

  // 진행 중인 job 폴링
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(async () => {
      try {
        const j = await api.job(job.job_id);
        setJob(j);
        if (j.status !== "running") {
          if (j.status === "auth_required") setLoginRequired(true);
          reload();
        }
      } catch (e) {
        setError(String(e));
      }
    }, 1500);
    return () => clearInterval(t);
  }, [job, reload]);

  const startScrape = async () => {
    setError(null);
    setLoginRequired(false);
    try {
      const { job_id } = await api.startScrape();
      setJob(await api.job(job_id));
    } catch (e) {
      if (e instanceof LoginRequiredError) setLoginRequired(true);
      else setError(String(e));
    }
  };

  // 같은 공고·플래그는 요청이 끝날 때까지 다시 토글하지 않는다 (중복 요청·롤백 경합 방지)
  const toggleFlag = async (p: Posting, flag: Flag) => {
    const key = `${flag}:${p.id}`;
    if (pending.current.has(key)) return;
    pending.current.add(key);
    const on = !p[flag];
    const set = (v: boolean) => setPostings((ps) => ps.map((x) => (x.id === p.id ? { ...x, [flag]: v } : x)));
    set(on);
    try {
      await FLAG_API[flag](p.id, on);
    } catch (e) {
      set(!on);
      setError(String(e));
    } finally {
      pending.current.delete(key);
    }
  };
  const toggleBookmark = (p: Posting) => toggleFlag(p, "bookmarked");
  const toggleHidden = (p: Posting) => toggleFlag(p, "hidden");

  const scraping = job?.status === "running";
  const count: Partial<Record<Tab, number>> = {
    bookmarks: postings.filter((p) => p.bookmarked && !p.hidden).length,
    hidden: postings.filter((p) => p.hidden).length,
  };
  const byId = Object.fromEntries(companies.map((c) => [c.company, c]));
  const phase =
    resumeFiles === null ? "loading"
    : resumeFiles.length === 0 || holdUpload ? "upload"
    : !companies.some((c) => c.interested) ? "select"
    : "main";

  return (
    <div className="container">
      <header>
        <Logo />
        <div>
          <h1>job-posting</h1>
          <p>등록 회사 채용 공고 중 나에게 맞는 포지션</p>
        </div>
      </header>

      {phase !== "main" && error && <div className="banner error">{error}</div>}

      {phase === "upload" && (
        <section className="panel onboarding">
          <h2>이력서 업로드</h2>
          <p className="meta">이력서를 기준으로 나에게 맞는 공고를 골라 등급을 매깁니다. 이력서·경력기술서·포트폴리오 등 여러 파일을 올릴 수 있습니다.</p>
          <ResumeDropzone onFiles={onboardingUpload} />
        </section>
      )}
      {phase === "select" && (
        <CompanySelect companies={companies} onConfirm={saveInterests} onEmpty={() => showToast("관심회사를 1개 이상 선택하세요", "error")} />
      )}
      {phase === "main" && (
        <>
          <nav className="tabs" role="tablist">
            {(["postings", "bookmarks", "hidden", "companies"] as Tab[]).map((t) => (
              <button key={t} className="tab" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
                {TAB_LABEL[t]}
                {!!count[t] && <span className="tab-count">{count[t]}</span>}
              </button>
            ))}
          </nav>

          {loginRequired && (
            <div className="banner">
              <strong>Claude 로그인이 필요합니다.</strong>
              <br />
              터미널에서 <code>claude login</code> 실행 후 다시 시도해주세요. 기존 공고는 계속 볼 수 있습니다.
            </div>
          )}
          {error && <div className="banner error">{error}</div>}

          {tab === "postings" && (
            <PostingsTab postings={postings} companies={companies} byId={byId} job={job} scraping={!!scraping}
                         onScrape={startScrape} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "bookmarks" && (
            <BookmarksTab postings={postings} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "hidden" && (
            <HiddenTab postings={postings} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "companies" && <CompaniesTab companies={companies} />}

          <ScrollTopButton />
        </>
      )}

      {toast && <Toast toast={toast} onClose={closeToast} />}
    </div>
  );
}
