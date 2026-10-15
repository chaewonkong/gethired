import { useState } from "react";
import { Company } from "../api";

interface Props {
  companies: Company[];
  onConfirm: (companies: string[]) => void;
  onEmpty: () => void;
}

export function CompanySelect({ companies, onConfirm, onEmpty }: Props) {
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (c: string) => setSelected((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c]));

  return (
    <section className="panel onboarding">
      <h2>관심회사 선택</h2>
      <p className="meta">선택한 회사의 공고만 보여주고 스크래핑합니다. 회사 탭에서 언제든 바꿀 수 있습니다.</p>
      <div className="company-select">
        {companies.map((c) => (
          <label key={c.company} className={selected.includes(c.company) ? "on" : undefined}>
            <input type="checkbox" checked={selected.includes(c.company)} onChange={() => toggle(c.company)} />
            <span className="co-logo">{c.display_name[0]}</span>
            {c.display_name}
          </label>
        ))}
      </div>
      <button type="button" className="btn" onClick={() => (selected.length ? onConfirm(selected) : onEmpty())}>
        확인{selected.length ? ` (${selected.length})` : ""}
      </button>
    </section>
  );
}
