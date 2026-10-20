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

export function Deadline({ deadline }: { deadline: string | null }) {
  const left = daysLeft(deadline);
  const soon = left !== null && left <= 7;
  return <div className={`deadline ${soon ? "soon" : ""}`}>{deadline ? `마감 ${deadline}${soon ? ` (D-${left})` : ""}` : "상시 채용"}</div>;
}

const stop = (e: MouseEvent) => e.stopPropagation();

export function StarButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      className={`star${on ? " on" : ""}`}
      aria-label={on ? "북마크 해제" : "북마크"}
      aria-pressed={on}
      onClick={(e) => (stop(e), onClick())}
    >
      <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinejoin="round">
        <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" />
      </svg>
    </button>
  );
}

export function HideButton({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      className={`hide${on ? " on" : ""}`}
      aria-label={on ? "숨김 해제" : "숨김"}
      aria-pressed={on}
      onClick={(e) => (stop(e), onClick())}
    >
      <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.6 5.1A9.8 9.8 0 0 1 12 5c5 0 8.5 4.5 9.5 7a13 13 0 0 1-2.3 3.4M6.6 6.6C4.5 8 3 10.2 2.5 12c1 2.5 4.5 7 9.5 7a9.6 9.6 0 0 0 5.4-1.6" />
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18" />
      </svg>
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
}

export function PostingCard({ posting: p, companyName, visible, onToggleBookmark, onToggleHidden }: Props) {
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
          <Deadline deadline={p.deadline} />
        </div>
        <span className={`level ${p.fit_level}`}>
          {p.fit_level} · {p.score}
        </span>
        <StarButton on={p.bookmarked} onClick={() => onToggleBookmark(p)} />
        <HideButton on={p.hidden} onClick={() => onToggleHidden(p)} />
      </div>
      <h3>{p.title}</h3>
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
        <a className="apply" href={p.apply_url} target="_blank" rel="noopener noreferrer" onClick={stop}>
          지원하기 →
        </a>
      </div>
    </article>
  );
}
