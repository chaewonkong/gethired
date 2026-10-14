import { FocusEvent, useEffect, useRef, useState } from "react";
import { Company } from "../api";

interface Props {
  companies: Company[];
  counts: Record<string, number>;
  excluded: string[];
  onChange: (excluded: string[]) => void;
}

function summary(selected: Company[], total: number): string {
  if (selected.length === total) return "전체 회사";
  if (selected.length === 0) return "선택 없음";
  if (selected.length === 1) return selected[0].display_name;
  return `${selected[0].display_name} 외 ${selected.length - 1}곳`;
}

export function CompanyFilter({ companies, counts, excluded, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const selected = companies.filter((c) => !excluded.includes(c.company));
  const allSelected = selected.length === companies.length;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = summary(selected, companies.length);
  const onBlur = (e: FocusEvent) => {
    if (e.relatedTarget && !root.current?.contains(e.relatedTarget)) setOpen(false);
  };

  const toggle = (company: string) =>
    onChange(excluded.includes(company) ? excluded.filter((c) => c !== company) : [...excluded, company]);

  return (
    <div className="company-filter" ref={root} onBlur={onBlur}>
      <button type="button" className="select-btn" aria-label={`회사 필터: ${label}`} aria-expanded={open} onClick={() => setOpen(!open)}>
        {label}
      </button>
      {open && (
        <div className="dropdown">
          <button type="button" className="toggle-all" onClick={() => onChange(allSelected ? companies.map((c) => c.company) : [])}>
            {allSelected ? "전체 끄기" : "전체 켜기"}
          </button>
          {companies.map((c) => {
            const n = counts[c.company] ?? 0;
            return (
              <label key={c.company} className={n === 0 ? "zero" : undefined}>
                <input type="checkbox" checked={!excluded.includes(c.company)} onChange={() => toggle(c.company)} />
                {c.display_name} <span className="count">{n}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
