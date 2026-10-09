import { useEffect, useRef, useState } from "react";
import { Company, Job, Level, LEVEL_RANK, Posting } from "../api";
import { PostingCard } from "./PostingCard";
import { ScrapeProgress } from "./ScrapeProgress";

interface Props {
  postings: Posting[];
  companies: Company[];
  byId: Record<string, Company>;
  job: Job | null;
  scraping: boolean;
  onScrape: () => void;
  onToggleBookmark: (p: Posting) => void;
}

function lastScrapedAt(companies: Company[]): string | null {
  const times = companies.map((c) => c.last_run?.finished_at).filter((t): t is string => !!t);
  return times.length ? times.sort().at(-1)! : null;
}

const PAGE_SIZE = 20;

export function PostingsTab({ postings, companies, byId, job, scraping, onScrape, onToggleBookmark }: Props) {
  const [company, setCompany] = useState("");
  const [minLevel, setMinLevel] = useState<Level>("stretch");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const sentinel = useRef<HTMLDivElement>(null);

  const items = postings
    .filter((p) => (!company || p.company === company) && LEVEL_RANK[p.fit_level] >= LEVEL_RANK[minLevel])
    .sort((a, b) => b.score - a.score);
  const last = lastScrapedAt(companies);
  const hasMore = visible < items.length;

  // 필터·데이터가 바뀌면 처음부터
  useEffect(() => {
    setVisible(PAGE_SIZE);
  }, [company, minLevel, postings]);

  // 바닥 sentinel이 보이면 다음 페이지
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setVisible((v) => v + PAGE_SIZE);
      },
      { rootMargin: "400px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, items.length]);

  return (
    <section className="panel">
      <div className="toolbar">
        <button className="btn" onClick={onScrape} disabled={scraping}>
          {scraping ? "스크래핑 중…" : "스크래핑 하기"}
        </button>
        <select value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">전체 회사</option>
          {companies.map((c) => (
            <option key={c.company} value={c.company}>{c.display_name}</option>
          ))}
        </select>
        <select value={minLevel} onChange={(e) => setMinLevel(e.target.value as Level)}>
          <option value="stretch">전체 등급</option>
          <option value="good">good 이상</option>
          <option value="strong">strong만</option>
        </select>
        <span className="meta">
          {items.length}건{last ? ` · 마지막 스크래핑 ${formatTime(last)}` : ""}
        </span>
      </div>

      {job && job.status === "running" && <ScrapeProgress job={job} byId={byId} />}
      {job && job.status !== "running" && <JobSummary job={job} />}

      <div className="list">
        {items.length ? (
          items.slice(0, visible).map((p) => (
            <PostingCard key={p.id} posting={p} companyName={byId[p.company]?.display_name ?? p.company} onToggleBookmark={onToggleBookmark} />
          ))
        ) : (
          <div className="empty">
            저장된 공고가 없습니다.
            <br />
            "스크래핑 하기"를 눌러 공고를 가져오세요.
          </div>
        )}
      </div>
      {hasMore && (
        <div ref={sentinel} className="sentinel">
          <span className="meta">{Math.min(visible, items.length)} / {items.length}건 · 더 불러오는 중…</span>
        </div>
      )}
    </section>
  );
}

function JobSummary({ job }: { job: Job }) {
  const s = Object.values(job.companies);
  const stored = s.reduce((n, c) => n + c.stored, 0);
  const judged = s.reduce((n, c) => n + c.new, 0);
  const failed = Object.entries(job.companies).filter(([, c]) => c.status === "failed").map(([k]) => k);
  return (
    <div className="progress show">
      <strong>스크래핑 완료</strong> · 신규 판정 {judged}건, 저장 {stored}건
      {failed.length > 0 && <> · 실패: {failed.join(", ")}</>}
      {job.cost_usd > 0 && <span className="meta"> · ${job.cost_usd.toFixed(2)} 상당</span>}
    </div>
  );
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
