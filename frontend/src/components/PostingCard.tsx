import { KeyboardEvent, MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Posting } from "../api";
import { saveListPosition } from "../sessionState";

function daysLeft(deadline: string | null): number | null {
  if (!deadline) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${deadline}T00:00:00`).getTime() - today.getTime()) / 86400000);
}

/** closed(공고 soft delete)면 D-day 대신 마감 배지 */
export function Deadline({ deadline, closed = false }: { deadline: string | null; closed?: boolean }) {
  if (closed) return <div className="deadline closed">마감</div>;
  const left = daysLeft(deadline);
  const soon = left !== null && left <= 7;
  return <div className={`deadline ${soon ? "soon" : ""}`}>{deadline ? `마감 ${deadline}${soon ? ` (D-${left})` : ""}` : "상시 채용"}</div>;
}

function localDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const stop = (e: MouseEvent) => e.stopPropagation();

interface ToggleProps {
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export function StarButton({ on, disabled, onClick }: ToggleProps) {
  return (
    <button
      className={`star${on ? " on" : ""}`}
      aria-label={on ? "북마크 해제" : "북마크"}
      aria-pressed={on}
      disabled={disabled}
      onClick={(e) => (stop(e), onClick())}
    >
      <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinejoin="round">
        <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" />
      </svg>
    </button>
  );
}

export function HideButton({ on, disabled, onClick }: ToggleProps) {
  return (
    <button
      className={`hide${on ? " on" : ""}`}
      aria-label={on ? "숨김 해제" : "숨김"}
      aria-pressed={on}
      disabled={disabled}
      onClick={(e) => (stop(e), onClick())}
    >
      <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.6 5.1A9.8 9.8 0 0 1 12 5c5 0 8.5 4.5 9.5 7a13 13 0 0 1-2.3 3.4M6.6 6.6C4.5 8 3 10.2 2.5 12c1 2.5 4.5 7 9.5 7a9.6 9.6 0 0 0 5.4-1.6" />
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18" />
      </svg>
    </button>
  );
}

export function AppliedButton({ on, disabled, onClick }: ToggleProps) {
  return (
    <button
      className={`applied${on ? " on" : ""}`}
      aria-label={on ? "지원완료 해제" : "지원완료"}
      aria-pressed={on}
      disabled={disabled}
      onClick={(e) => (stop(e), onClick())}
    >
      <svg viewBox="0 0 24 24" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M8.3 12.4l2.5 2.5 4.9-5.2" />
      </svg>
      <span>지원완료</span>
    </button>
  );
}

interface Props {
  posting: Posting;
  companyName: string;
  /** 무한 스크롤 목록이면 불러온 건수. 상세에서 돌아올 때 복원한다 */
  visible?: number;
  onToggleBookmark: (p: Posting) => void;
  onToggleHidden: (p: Posting) => void;
  onToggleApplied: (p: Posting) => void;
}

export function PostingCard({ posting: p, companyName, visible, onToggleBookmark, onToggleHidden, onToggleApplied }: Props) {
  // 마감 공고는 지원완료 해제만 가능하다 (북마크·숨김은 서버가 404)
  const closed = p.deleted_at !== null;
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // 이동 전에 저장한다 (unmount 시점에는 DOM이 바뀌어 scrollY가 0)
  const open = () => {
    saveListPosition(pathname, { scrollY: window.scrollY, visible: visible ?? null });
    navigate(`/postings/${p.id}`);
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && e.target === e.currentTarget) open();
  };

  return (
    <article className="card" role="link" tabIndex={0} aria-label={p.title} onClick={open} onKeyDown={onKeyDown}>
      <div className="card-head">
        <div className="co-logo">{companyName[0]}</div>
        <div className="co-info">
          <div className="company">{companyName}</div>
          <Deadline deadline={p.deadline} closed={closed} />
        </div>
        <span className={`level ${p.fit_level}`}>
          {p.fit_level} · {p.score}
        </span>
        <StarButton on={p.bookmarked} disabled={closed} onClick={() => onToggleBookmark(p)} />
        <HideButton on={p.hidden} disabled={closed} onClick={() => onToggleHidden(p)} />
      </div>
      <h3>{p.title}</h3>
      {p.application && (
        <div className="applied-at">
          {p.application.stage ?? "지원완료"} · {localDate(p.application.applied_at)}
        </div>
      )}
      <p className="summary">{p.summary}</p>
      {p.tech_stack.length > 0 && (
        <div className="chips">
          {p.tech_stack.map((s) => (
            <span key={s} className="chip">{s}</span>
          ))}
        </div>
      )}
      {p.gaps.length > 0 && (
        <ul className="gaps">
          {p.gaps.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      )}
      <p className="reason">
        <strong>추천 이유</strong>
        {p.fit_reason}
      </p>
      <div className="card-foot">
        <span className="meta">수집 {p.first_seen_at.slice(0, 10)}</span>
        <div className="actions">
          <a className="apply" href={p.apply_url} target="_blank" rel="noopener noreferrer" onClick={stop}>
            지원하기 →
          </a>
          <AppliedButton on={p.application !== null} disabled={closed && p.application === null} onClick={() => onToggleApplied(p)} />
        </div>
      </div>
    </article>
  );
}
