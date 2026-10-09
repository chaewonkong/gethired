import { useCallback, useEffect, useState } from "react";
import { api, Company, Job, LoginRequiredError, Posting } from "./api";
import { Logo } from "./components/Logo";
import { PostingsTab } from "./components/PostingsTab";
import { BookmarksTab } from "./components/BookmarksTab";
import { CompaniesTab } from "./components/CompaniesTab";
import { ScrollTopButton } from "./components/ScrollTopButton";

type Tab = "postings" | "bookmarks" | "companies";

const TAB_LABEL: Record<Tab, string> = { postings: "공고", bookmarks: "북마크", companies: "회사" };

export default function App() {
  const [tab, setTab] = useState<Tab>("postings");
  const [postings, setPostings] = useState<Posting[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [loginRequired, setLoginRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const toggleBookmark = async (p: Posting) => {
    const on = !p.bookmarked;
    const set = (v: boolean) => setPostings((ps) => ps.map((x) => (x.id === p.id ? { ...x, bookmarked: v } : x)));
    set(on);
    try {
      await api.setBookmark(p.id, on);
    } catch (e) {
      set(!on);
      setError(String(e));
    }
  };

  const scraping = job?.status === "running";
  const bookmarkCount = postings.filter((p) => p.bookmarked).length;
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
        {(["postings", "bookmarks", "companies"] as Tab[]).map((t) => (
          <button key={t} className="tab" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {TAB_LABEL[t]}
            {t === "bookmarks" && bookmarkCount > 0 && <span className="tab-count">{bookmarkCount}</span>}
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
                     onScrape={startScrape} onToggleBookmark={toggleBookmark} />
      )}
      {tab === "bookmarks" && <BookmarksTab postings={postings} byId={byId} onToggleBookmark={toggleBookmark} />}
      {tab === "companies" && <CompaniesTab companies={companies} />}

      <ScrollTopButton />
    </div>
  );
}
