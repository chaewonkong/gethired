import { useEffect, useRef, useState } from "react";
import { Company, Job, Level, LEVEL_RANK, Posting } from "../api";
import { useListPosition, useSessionState } from "../sessionState";
import { CompanyFilter } from "./CompanyFilter";
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
  onToggleHidden: (p: Posting) => void;
}

function lastScrapedAt(companies: Company[]): string | null {
  const times = companies.map((c) => c.last_run?.finished_at).filter((t): t is string => !!t);
  return times.length ? times.sort().at(-1)! : null;
}

const PAGE_SIZE = 20;

type Sort = "score" | "newest" | "oldest";
const SORTS: Record<Sort, string> = { score: "적합도순", newest: "최신순", oldest: "오래된순" };

const byScore = (a: Posting, b: Posting) => b.score - a.score;
const seen = (p: Posting) => Date.parse(p.first_seen_at);
const COMPARE: Record<Sort, (a: Posting, b: Posting) => number> = {
  score: byScore,
  newest: (a, b) => seen(b) - seen(a) || byScore(a, b),
  oldest: (a, b) => seen(a) - seen(b) || byScore(a, b),
};

const parseCompanies = (raw: unknown) => (Array.isArray(raw) && raw.every((c) => typeof c === "string") ? raw : null);
const parseLevel = (raw: unknown) => (typeof raw === "string" && Object.hasOwn(LEVEL_RANK, raw) ? (raw as Level) : null);
const parseSort = (raw: unknown) => (typeof raw === "string" && Object.hasOwn(SORTS, raw) ? (raw as Sort) : null);

export function PostingsTab({ postings, companies, byId, job, scraping, onScrape, onToggleBookmark, onToggleHidden }: Props) {
  // 해제한 회사를 저장해 새로 추가된 회사는 기본 선택 상태가 되게 한다
  const [excluded, setExcluded] = useSessionState<string[]>("postings.excludedCompanies", [], parseCompanies);
  const [minLevel, setMinLevel] = useSessionState<Level>("postings.minLevel", "stretch", parseLevel);
  const [sort, setSort] = useSessionState<Sort>("postings.sort", "score", parseSort);
  const sentinel = useRef<HTMLDivElement>(null);

  const leveled = postings.filter((p) => !p.hidden && LEVEL_RANK[p.fit_level] >= LEVEL_RANK[minLevel]);
  const counts: Record<string, number> = {};
  for (const p of leveled) counts[p.company] = (counts[p.company] ?? 0) + 1;
  const selected = new Set(companies.map((c) => c.company).filter((c) => !excluded.includes(c)));
  const items = leveled.filter((p) => selected.has(p.company)).sort(COMPARE[sort]);
  const noneSelected = companies.length > 0 && selected.size === 0;
  const last = lastScrapedAt(companies);
  const restored = useListPosition("/", items.length > 0);
  const [visible, setVisible] = useState(restored?.visible ?? PAGE_SIZE);
  const hasMore = visible < items.length;

  // 필터가 바뀌면 처음부터. 북마크·숨김 토글로 postings가 바뀔 때는 스크롤 위치 유지. mount 때는 복원값을 지킨다
  const filters = useRef({ excluded, minLevel, sort });
  useEffect(() => {
    const prev = filters.current;
    if (prev.excluded === excluded && prev.minLevel === minLevel && prev.sort === sort) return;
    filters.current = { excluded, minLevel, sort };
    setVisible(PAGE_SIZE);
  }, [excluded, minLevel, sort]);

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
        <CompanyFilter companies={companies} counts={counts} excluded={excluded} onChange={setExcluded} />
        <select value={minLevel} onChange={(e) => setMinLevel(e.target.value as Level)}>
          <option value="stretch">전체 등급</option>
          <option value="good">good 이상</option>
          <option value="strong">strong만</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="정렬">
          {(Object.keys(SORTS) as Sort[]).map((s) => (
            <option key={s} value={s}>{SORTS[s]}</option>
          ))}
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
            <PostingCard key={p.id} posting={p} companyName={byId[p.company]?.display_name ?? p.company} visible={visible} onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} />
          ))
        ) : noneSelected ? (
          <div className="empty">
            선택된 회사가 없습니다.
            <br />
            회사 필터에서 보고 싶은 회사를 선택하세요.
          </div>
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
