import { Company, Job } from "../api";

export function ScrapeProgress({ job, byId }: { job: Job; byId: Record<string, Company> }) {
  return (
    <div className="progress show">
      <strong>스크래핑 중…</strong>
      <ul>
        {Object.entries(job.companies).map(([name, c]) => (
          <li key={name}>
            <span className={`dot ${c.status}`} />
            {byId[name]?.display_name ?? name}
            {c.status === "running" && c.new > 0 && <span className="meta"> · {c.new}건 판정 중</span>}
            {c.status === "done" && <span className="meta"> · {c.stored}건 저장</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
