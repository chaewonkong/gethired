import { KeyboardEvent, useId, useRef } from "react";
import { AuthStatus, Provider } from "../api";

export const PROVIDERS: { id: Provider; name: string; desc: string }[] = [
  { id: "claude", name: "Claude Code", desc: "Claude Code 세션으로 프로필 추출·판정. 비용이 표시됩니다" },
  { id: "codex", name: "Codex", desc: "Codex CLI 구독 세션으로 실행. 비용은 표시되지 않습니다" },
];
export const PROVIDER_NAME: Record<Provider, string> = Object.fromEntries(PROVIDERS.map((p) => [p.id, p.name])) as Record<Provider, string>;

interface Props {
  value: Provider;
  auth: AuthStatus | null;
  disabled?: boolean;
  onSelect: (provider: Provider) => void;
}

/** 선택된 카드의 배지. auth가 없거나 다른 provider 것이면 확인 중 */
function Badge({ auth, provider }: { auth: AuthStatus | null; provider: Provider }) {
  if (!auth || auth.provider !== provider) return <span className="provider-badge">확인 중</span>;
  if (auth.logged_in) return <span className="provider-badge ok">로그인됨</span>;
  return (
    <span className="provider-badge need">
      로그인 필요 · 터미널에서 <code>{auth.login_command}</code>
    </span>
  );
}

export function ProviderPicker({ value, auth, disabled = false, onSelect }: Props) {
  const uid = useId();
  const cards = useRef<(HTMLDivElement | null)[]>([]);

  const select = (p: Provider) => {
    if (!disabled) onSelect(p);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>, i: number) => {
    const n = PROVIDERS.length;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") cards.current[(i + 1) % n]?.focus();
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") cards.current[(i - 1 + n) % n]?.focus();
    else if (e.key === "Enter" || e.key === " ") select(PROVIDERS[i].id);
    else return;
    e.preventDefault();
  };

  return (
    <div className="provider-picker-wrap">
      <div className="provider-picker" role="radiogroup" aria-label="AI 선택" aria-disabled={disabled || undefined}>
        {PROVIDERS.map((p, i) => {
          const on = value === p.id;
          const nameId = `${uid}-${p.id}-name`;
          const descId = `${uid}-${p.id}-desc`;
          return (
            <div
              key={p.id}
              ref={(el) => {
                cards.current[i] = el;
              }}
              role="radio"
              aria-checked={on}
              aria-labelledby={nameId}
              aria-describedby={descId}
              aria-disabled={disabled || undefined}
              tabIndex={on ? 0 : -1}
              className={`provider-card${on ? " on" : ""}`}
              onClick={() => select(p.id)}
              onKeyDown={(e) => onKey(e, i)}
            >
              <span id={nameId} className="provider-name">{p.name}</span>
              <span id={descId} className="meta">{p.desc}</span>
              {on && <Badge auth={auth} provider={p.id} />}
            </div>
          );
        })}
      </div>
      {disabled && <p className="meta provider-notice">스크래핑 중에는 바꿀 수 없습니다</p>}
    </div>
  );
}
