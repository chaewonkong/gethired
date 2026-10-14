import { useCallback, useEffect, useRef, useState } from "react";
import { api, Company, Job, LoginRequiredError, Posting } from "./api";
import { Logo } from "./components/Logo";
import { PostingsTab } from "./components/PostingsTab";
import { BookmarksTab } from "./components/BookmarksTab";
import { HiddenTab } from "./components/HiddenTab";
import { CompaniesTab } from "./components/CompaniesTab";
import { ScrollTopButton } from "./components/ScrollTopButton";

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
  const pending = useRef(new Set<string>());

  const reload = useCallback(async () => {
    try {
      const [p, c] = await Promise.all([api.postings(), api.companies()]);
      setPostings(p);
      setCompanies(c);
    } catch (e) {
      setError(String(e));
    }
  }, []);

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

  return (
    <div className="container">
      <header>
        <Logo />
        <div>
          <h1>job-posting</h1>
          <p>등록 회사 채용 공고 중 나에게 맞는 포지션</p>
        </div>
      </header>

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
    </div>
  );
}
