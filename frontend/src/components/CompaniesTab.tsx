import { Company, ScrapeRun } from "../api";
import { formatTime } from "./PostingsTab";

function Status({ run }: { run: ScrapeRun | null }) {
  if (!run) return <span className="status">기록 없음</span>;
  if (run.status === "done") return <span className="status ok">성공 · {run.fetched_count ?? 0}건</span>;
  if (run.status === "running") return <span className="status">진행 중</span>;
  if (run.status === "auth_required") return <span className="status fail">로그인 필요</span>;
  return <span className="status fail">실패 · {run.error ?? "원인 불명"}</span>;
}

interface Props {
  companies: Company[];
  onToggleInterest: (c: Company) => void;
}

export function CompaniesTab({ companies, onToggleInterest }: Props) {
  return (
    <section className="panel">
      <table className="company-table">
        <thead>
          <tr>
            <th>회사</th>
            <th>채용사이트</th>
            <th>마지막 결과</th>
            <th>마지막 스크래핑</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => (
            <tr key={c.company}>
              <td className="name">
                <button
                  className={`star${c.interested ? " on" : ""}`}
                  aria-label={c.interested ? `${c.display_name} 관심회사 해제` : `${c.display_name} 관심회사 추가`}
                  aria-pressed={c.interested}
                  onClick={() => onToggleInterest(c)}
                >
                  <svg viewBox="0 0 24 24" strokeWidth="1.8" strokeLinejoin="round">
                    <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" />
                  </svg>
                </button>
                <span className="co-logo">{c.display_name[0]}</span>
                {c.display_name}
              </td>
              <td>
                <a href={c.careers_url} target="_blank" rel="noopener noreferrer">
                  {c.careers_url.replace(/^https?:\/\//, "")}
                </a>
              </td>
              <td><Status run={c.last_run} /></td>
              <td className="meta">{c.last_run?.finished_at ? formatTime(c.last_run.finished_at) : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
