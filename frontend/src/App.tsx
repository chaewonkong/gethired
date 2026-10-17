import { useCallback, useEffect, useRef, useState } from "react";
import { api, AuthStatus, Company, Job, JobRunningError, LoginRequiredError, Posting, Provider, ProviderSetting, ResumeFile } from "./api";
import { Logo } from "./components/Logo";
import { PostingsTab } from "./components/PostingsTab";
import { BookmarksTab } from "./components/BookmarksTab";
import { HiddenTab } from "./components/HiddenTab";
import { CompaniesTab } from "./components/CompaniesTab";
import { ScrollTopButton } from "./components/ScrollTopButton";
import { CompanySelect } from "./components/CompanySelect";
import { ProviderSelect } from "./components/ProviderSelect";
import { invalidResumeFiles, ResumeDropzone } from "./components/ResumeDropzone";
import { ResumeModal } from "./components/ResumeModal";
import { Toast, ToastMessage } from "./components/Toast";

type Tab = "postings" | "bookmarks" | "hidden" | "companies";

const TAB_LABEL: Record<Tab, string> = { postings: "공고", bookmarks: "북마크", hidden: "숨김", companies: "회사" };
export const AUTH_POLL_MS = 3000;

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
  const [resumeOpen, setResumeOpen] = useState(false);
  const [setting, setSetting] = useState<ProviderSetting | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const pending = useRef(new Set<string>());
  const toastSeq = useRef(0);
  const provider = setting?.provider;
  const providerRef = useRef(provider);
  providerRef.current = provider;

  const reload = useCallback(async () => {
    try {
      const [p, c, r, s] = await Promise.all([api.postings(), api.companies(), api.resumeFiles(), api.providerSetting()]);
      setPostings(p);
      setCompanies(c);
      setResumeFiles(r);
      setSetting(s);
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

  const managerUpload = async (files: File[]) => {
    if (await uploadResumes(files)) showToast("이력서를 업로드했습니다", "ok");
  };

  // 마지막 파일을 지우면 phase 계산에 따라 업로드 화면으로 간다
  const deleteResume = async (name: string) => {
    try {
      await api.deleteResume(name);
    } catch (e) {
      setError(String(e));
    }
    try {
      const files = await api.resumeFiles();
      setResumeFiles(files);
      if (!files.length) setResumeOpen(false);
    } catch (e) {
      setError(String(e));
    }
  };
  const closeResume = useCallback(() => setResumeOpen(false), []);

  const saveInterests = async (selected: string[]) => {
    try {
      await api.setInterests(selected);
      setCompanies(await api.companies());
      setTab("postings");
    } catch (e) {
      setError(String(e));
    }
  };

  // 선택은 먼저 바꾸고 PUT. 실패하면 되돌린다. 요청 중 중복 선택은 무시
  const selectProvider = async (p: Provider): Promise<boolean> => {
    const prev = setting;
    if (!prev || pending.current.has("provider")) return false;
    pending.current.add("provider");
    setSetting({ ...prev, provider: p });
    try {
      setAuth(await api.setProvider(p));
      return true;
    } catch (e) {
      setSetting((s) => (s ? { ...s, provider: prev.provider } : s));
      if (e instanceof JobRunningError) showToast(e.message, "error");
      else setError(String(e));
      return false;
    } finally {
      pending.current.delete("provider");
    }
  };
  const finishProviderStep = () => setSetting((s) => (s ? { ...s, chosen: true } : s));

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
  // 마지막 관심회사를 해제하면 phase 계산에 따라 회사 선택 화면으로 간다
  const toggleInterest = async (c: Company) => {
    const key = `interest:${c.company}`;
    if (pending.current.has(key)) return;
    pending.current.add(key);
    const on = !c.interested;
    const set = (v: boolean) => setCompanies((cs) => cs.map((x) => (x.company === c.company ? { ...x, interested: v } : x)));
    set(on);
    try {
      await api.setInterest(c.company, on);
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
  // 관심회사가 아닌 회사의 공고는 모든 탭·배지에서 뺀다 (DB에는 남아 있음)
  const interested = companies.filter((c) => c.interested);
  const interestSet = new Set(interested.map((c) => c.company));
  const shown = postings.filter((p) => interestSet.has(p.company));
  const count: Partial<Record<Tab, number>> = {
    bookmarks: shown.filter((p) => p.bookmarked && !p.hidden).length,
    hidden: shown.filter((p) => p.hidden).length,
  };
  const byId = Object.fromEntries(companies.map((c) => [c.company, c]));
  const phase =
    resumeFiles === null || setting === null ? "loading"
    : resumeFiles.length === 0 || holdUpload ? "upload"
    : !setting.chosen ? "provider"
    : interested.length === 0 ? "select"
    : "main";

  // provider 화면이 보이고 아직 로그인 전이면 로그인 상태를 폴링한다. 응답 후 3초 뒤 재조회, 다른 provider 응답은 버린다
  const loggedIn = !!auth && auth.provider === provider && auth.logged_in;
  const watchAuth = phase === "provider" && !loggedIn;
  useEffect(() => {
    if (!watchAuth) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const a = await api.authStatus();
        if (cancelled) return;
        if (a.provider === providerRef.current) setAuth(a);
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
      }
      timer = setTimeout(tick, AUTH_POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [watchAuth, provider]);

  return (
    <div className="container">
      <header>
        <Logo />
        <div>
          <h1>job-posting</h1>
          <p>등록 회사 채용 공고 중 나에게 맞는 포지션</p>
        </div>
        {phase === "main" && (
          <button type="button" className="header-btn" onClick={() => setResumeOpen(true)}>
            이력서
          </button>
        )}
      </header>

      {phase !== "main" && error && <div className="banner error">{error}</div>}

      {phase === "upload" && (
        <section className="panel onboarding">
          <h2>이력서 업로드</h2>
          <p className="meta">이력서를 기준으로 나에게 맞는 공고를 골라 등급을 매깁니다. 이력서·경력기술서·포트폴리오 등 여러 파일을 올릴 수 있습니다.</p>
          <ResumeDropzone onFiles={onboardingUpload} />
        </section>
      )}
      {phase === "provider" && setting && (
        <ProviderSelect setting={setting} auth={auth} onSelect={selectProvider} onContinue={finishProviderStep} />
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
            <PostingsTab postings={shown} companies={interested} byId={byId} job={job} scraping={!!scraping}
                         onScrape={startScrape} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "bookmarks" && (
            <BookmarksTab postings={shown} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "hidden" && (
            <HiddenTab postings={shown} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} />
          )}
          {tab === "companies" && <CompaniesTab companies={companies} onToggleInterest={toggleInterest} />}

          <ScrollTopButton />
          {resumeOpen && resumeFiles && (
            <ResumeModal files={resumeFiles} onUpload={managerUpload} onDelete={deleteResume} onClose={closeResume} />
          )}
        </>
      )}

      {toast && <Toast toast={toast} onClose={closeToast} />}
    </div>
  );
}
