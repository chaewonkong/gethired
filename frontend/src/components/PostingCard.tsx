import { Posting } from "../api";

function daysLeft(deadline: string | null): number | null {
  if (!deadline) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((new Date(deadline).getTime() - today.getTime()) / 86400000);
}

interface Props {
  posting: Posting;
  companyName: string;
  onToggleBookmark: (p: Posting) => void;
}

export function PostingCard({ posting: p, companyName, onToggleBookmark }: Props) {
  const left = daysLeft(p.deadline);
  const soon = left !== null && left <= 7;
  const deadlineText = p.deadline ? `마감 ${p.deadline}${soon ? ` (D-${left})` : ""}` : "상시 채용";

  return (
    <article className="card">
      <div className="card-head">
        <div className="co-logo">{companyName[0]}</div>
        <div className="co-info">
          <div className="company">{companyName}</div>
          <div className={`deadline ${soon ? "soon" : ""}`}>{deadlineText}</div>
        </div>
        <span className={`level ${p.fit_level}`}>
          {p.fit_level} · {p.score}
        </span>
        <button
          className={`star${p.bookmarked ? " on" : ""}`}
          aria-label={p.bookmarked ? "북마크 해제" : "북마크"}
          aria-pressed={p.bookmarked}
          onClick={() => onToggleBookmark(p)}
        >
          <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinejoin="round">
            <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" />
          </svg>
        </button>
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
        <span className="meta">수집 {p.scraped_at.slice(0, 10)}</span>
        <a className="apply" href={p.apply_url} target="_blank" rel="noopener noreferrer">
          지원하기 →
        </a>
      </div>
    </article>
  );
}
