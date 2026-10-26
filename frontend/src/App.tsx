import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, Application, AuthStatus, Company, Job, JobRunningError, LoginRequiredError, Posting, Provider, ProviderSetting, ResumeFile, ResumeRejectedError } from "./api";
import { Logo } from "./components/Logo";
import { PostingsTab } from "./components/PostingsTab";
import { BookmarksTab } from "./components/BookmarksTab";
import { AppliedTab } from "./components/AppliedTab";
import { HiddenTab } from "./components/HiddenTab";
import { CompaniesTab } from "./components/CompaniesTab";
import { PostingDetail } from "./components/PostingDetail";
import { ScrollTopButton } from "./components/ScrollTopButton";
import { CompanySelect } from "./components/CompanySelect";
import { ProviderSelect } from "./components/ProviderSelect";
import { ProviderModal } from "./components/ProviderModal";
import { PROVIDER_NAME } from "./components/ProviderPicker";
import { invalidResumeFiles, ResumeDropzone } from "./components/ResumeDropzone";
import { ResumeModal } from "./components/ResumeModal";
import { Toast, ToastMessage } from "./components/Toast";

type Tab = "postings" | "bookmarks" | "applied" | "hidden" | "companies";

const TAB_LABEL: Record<Tab, string> = { postings: "공고", bookmarks: "북마크", applied: "지원완료", hidden: "숨김", companies: "회사" };
const TAB_PATH: Record<Tab, string> = { postings: "/", bookmarks: "/bookmarks", applied: "/applied", hidden: "/hidden", companies: "/companies" };
const TABS = Object.keys(TAB_PATH) as Tab[];
export const AUTH_POLL_MS = 3000;

// 낙관적 업데이트로 토글하는 공고 플래그와 그 저장 API
const FLAG_API = { bookmarked: api.setBookmark, hidden: api.setHidden } satisfies Record<string, (id: number, on: boolean) => Promise<void>>;
type Flag = keyof typeof FLAG_API;

export default function App() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const tab = TABS.find((t) => TAB_PATH[t] === pathname);
  const [postings, setPostings] = useState<Posting[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  // 스크래핑 401·auth_required 배너. message는 401 body 문구 (auth 응답이 없을 때 대신 보여줌)
  const [loginRequired, setLoginRequired] = useState<{ message: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumeFiles, setResumeFiles] = useState<ResumeFile[] | null>(null);
  const [toast, setToast] = useState<(ToastMessage & { after?: () => void }) | null>(null);
  // 온보딩 업로드 직후 toast가 닫힐 때까지 업로드 화면에 머문다
  const [holdUpload, setHoldUpload] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
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

  // 서버가 400으로 거부한 파일은 toast로 알리고 나머지는 계속 올린다. 모두 올라갔을 때만 true
  const uploadResumes = async (files: File[]): Promise<boolean> => {
    const invalid = invalidResumeFiles(files);
    if (invalid) {
      showToast(invalid, "error");
      return false;
    }
    const rejected: string[] = [];
    try {
      for (const f of files) {
        try {
          await api.putResume(f.name, f);
        } catch (e) {
          if (!(e instanceof ResumeRejectedError)) throw e;
          rejected.push(e.message);
        }
      }
      if (rejected.length) showToast(rejected.join(" / "), "error");
      return rejected.length === 0;
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
  const closeAi = useCallback(() => setAiOpen(false), []);

  const saveInterests = async (selected: string[]) => {
    try {
      await api.setInterests(selected);
      setCompanies(await api.companies());
      navigate("/");
    } catch (e) {
      setError(String(e));
    }
  };

  // 현재 provider가 로그인돼 있으면 로그인 배너는 의미가 없다
  const applyAuth = (a: AuthStatus) => {
    setAuth(a);
    if (a.logged_in) setLoginRequired(null);
  };
  // 서버가 미로그인이라 했으니 알고 있던 상태를 버리고 다시 확인한다
  const requireLogin = (message: string | null) => {
    setLoginRequired({ message });
    setAuth(null);
  };

  // 선택은 먼저 바꾸고 PUT. 실패하면 되돌린다. 요청 중 중복 선택은 무시
  const selectProvider = async (p: Provider): Promise<boolean> => {
    const prev = setting;
    if (!prev || pending.current.has("provider")) return false;
    pending.current.add("provider");
    setSetting({ ...prev, provider: p });
    try {
      applyAuth(await api.setProvider(p));
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
          if (j.status === "auth_required") requireLogin(null);
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
    setLoginRequired(null);
    try {
      const { job_id } = await api.startScrape();
      setJob(await api.job(job_id));
    } catch (e) {
      if (e instanceof LoginRequiredError) requireLogin(e.message);
      else if (e instanceof JobRunningError) showToast("다른 곳에서 스크래핑 중입니다", "error");
      else setError(String(e));
    }
  };

  // 같은 공고·플래그는 요청이 끝날 때까지 다시 토글하지 않는다 (중복 요청·롤백 경합 방지). 저장됐으면 true
  const toggleFlag = async (p: Posting, flag: Flag): Promise<boolean> => {
    const key = `${flag}:${p.id}`;
    if (pending.current.has(key)) return false;
    pending.current.add(key);
    const on = !p[flag];
    const set = (v: boolean) => setPostings((ps) => ps.map((x) => (x.id === p.id ? { ...x, [flag]: v } : x)));
    set(on);
    try {
      await FLAG_API[flag](p.id, on);
      return true;
    } catch (e) {
      set(!on);
      setError(String(e));
      return false;
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

  // 지원완료는 리소스라 toggleFlag와 별도. 켜기는 PUT 응답의 지원 시각으로 교체, 마감 공고 해제는 되돌릴 수 없어 확인을 받는다
  const toggleApplied = async (p: Posting): Promise<boolean> => {
    const key = `application:${p.id}`;
    if (pending.current.has(key)) return false;
    const on = p.application === null;
    if (!on && p.deleted_at !== null && !window.confirm("마감된 공고라 해제하면 다시 볼 수 없습니다. 해제할까요?")) return false;
    pending.current.add(key);
    const set = (v: Application | null) => setPostings((ps) => ps.map((x) => (x.id === p.id ? { ...x, application: v } : x)));
    set(on ? { applied_at: new Date().toISOString(), stage: null } : null);
    try {
      if (on) set(await api.setApplied(p.id));
      else await api.clearApplied(p.id);
      return true;
    } catch (e) {
      set(p.application);
      setError(String(e));
      return false;
    } finally {
      pending.current.delete(key);
    }
  };

  const scraping = job?.status === "running";
  // 마감 공고는 지원완료인 것만 남긴다 (서버도 그렇게 주지만, 해제 직후 로컬 행이 다른 탭에 나타나지 않게)
  const live = postings.filter((p) => p.deleted_at === null || p.application !== null);
  // 관심회사가 아닌 회사의 공고는 모든 탭·배지에서 뺀다 (DB에는 남아 있음). 지원완료 탭은 이력이라 예외
  const interested = companies.filter((c) => c.interested);
  const interestSet = new Set(interested.map((c) => c.company));
  const shown = live.filter((p) => interestSet.has(p.company) && p.application === null);
  const appliedAt = (p: Posting) => Date.parse(p.application!.applied_at);
  const applied = live.filter((p) => p.application !== null).sort((a, b) => appliedAt(b) - appliedAt(a) || b.id - a.id);
  const count: Partial<Record<Tab, number>> = {
    bookmarks: shown.filter((p) => p.bookmarked && !p.hidden).length,
    applied: applied.length,
    hidden: shown.filter((p) => p.hidden).length,
  };
  const byId = Object.fromEntries(companies.map((c) => [c.company, c]));
  const phase =
    resumeFiles === null || setting === null ? "loading"
    : resumeFiles.length === 0 || holdUpload ? "upload"
    : !setting.chosen ? "provider"
    : interested.length === 0 ? "select"
    : "main";

  // provider 화면·AI 모달·로그인 배너가 보이고 아직 로그인 전이면 로그인 상태를 폴링한다. 응답 후 3초 뒤 재조회, 다른 provider 응답은 버린다
  const loggedIn = !!auth && auth.provider === provider && auth.logged_in;
  const watchAuth = (phase === "provider" || aiOpen || !!loginRequired) && !loggedIn;
  useEffect(() => {
    if (!watchAuth) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const a = await api.authStatus();
        if (cancelled) return;
        if (a.provider === providerRef.current) {
          applyAuth(a);
          if (a.logged_in) return; // effect cleanup을 기다리지 않고 여기서 폴링을 멈춘다
        }
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
          <h1 className="brand" aria-label="get-hired">
            <span className="brand-get">get</span>hired
          </h1>
          <p>등록 회사 채용 공고 중 나에게 맞는 포지션</p>
        </div>
        {phase === "main" && (
          <div className="header-actions">
            <button type="button" className="header-btn" onClick={() => setResumeOpen(true)}>
              이력서
            </button>
            <button type="button" className="header-btn" onClick={() => setAiOpen(true)}>
              AI
            </button>
          </div>
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
            {TABS.map((t) => (
              <button key={t} className="tab" role="tab" aria-selected={tab === t} onClick={() => navigate(TAB_PATH[t])}>
                {TAB_LABEL[t]}
                {!!count[t] && <span className="tab-count">{count[t]}</span>}
              </button>
            ))}
          </nav>

          {loginRequired && setting && (
            <div className="banner">
              <strong>{PROVIDER_NAME[setting.provider]} 로그인이 필요합니다.</strong>
              <br />
              {auth && auth.provider === setting.provider ? (
                <>터미널에서 <code>{auth.login_command}</code> 실행 후 다시 시도해주세요.</>
              ) : (
                loginRequired.message
              )}{" "}
              기존 공고는 계속 볼 수 있습니다.
              <button type="button" className="banner-btn" onClick={() => setAiOpen(true)}>AI 변경</button>
            </div>
          )}
          {error && <div className="banner error">{error}</div>}

          <Routes>
            <Route path="/" element={
              <PostingsTab postings={shown} companies={interested} byId={byId} job={job} scraping={!!scraping} onScrape={startScrape}
                           onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} onToggleApplied={toggleApplied} />
            } />
            <Route path="/bookmarks" element={<BookmarksTab postings={shown} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} onToggleApplied={toggleApplied} />} />
            <Route path="/applied" element={<AppliedTab postings={applied} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} onToggleApplied={toggleApplied} />} />
            <Route path="/hidden" element={<HiddenTab postings={shown} byId={byId} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden} onToggleApplied={toggleApplied} />} />
            <Route path="/companies" element={<CompaniesTab companies={companies} onToggleInterest={toggleInterest} />} />
            <Route path="/postings/:id" element={
              <PostingDetail postings={postings} byId={byId} loginRequired={!!loginRequired} onToggleBookmark={toggleBookmark} onToggleHidden={toggleHidden}
                             onToggleApplied={toggleApplied} onRequireLogin={requireLogin} onToast={showToast} />
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          <ScrollTopButton />
          {resumeOpen && resumeFiles && (
            <ResumeModal files={resumeFiles} onUpload={managerUpload} onDelete={deleteResume} onClose={closeResume} />
          )}
          {aiOpen && setting && (
            <ProviderModal value={setting.provider} auth={auth} disabled={!!scraping} onSelect={selectProvider} onClose={closeAi} />
          )}
        </>
      )}

      {toast && <Toast toast={toast} onClose={closeToast} />}
    </div>
  );
}
