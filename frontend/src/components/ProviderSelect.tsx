import { useState } from "react";
import { AuthStatus, Provider, ProviderSetting } from "../api";
import { ProviderPicker } from "./ProviderPicker";

interface Props {
  setting: ProviderSetting;
  auth: AuthStatus | null;
  onSelect: (provider: Provider) => Promise<boolean>;
  onContinue: () => void;
}

/** 온보딩 AI 선택. 카드 선택 시 저장, "계속"은 아직 저장 안 했으면 현재 선택을 저장하고 진행 */
export function ProviderSelect({ setting, auth, onSelect, onContinue }: Props) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const select = async (p: Provider) => {
    if (await onSelect(p)) setSaved(true);
  };
  const next = async () => {
    if (saved) return onContinue();
    setBusy(true);
    const ok = await onSelect(setting.provider);
    setBusy(false);
    if (ok) onContinue();
  };

  return (
    <section className="panel onboarding">
      <h2>AI 선택</h2>
      <p className="meta">프로필 추출과 공고 판정에 쓸 AI를 고릅니다. 로그인하지 않아도 계속할 수 있고, 헤더의 AI 버튼으로 언제든 바꿀 수 있습니다.</p>
      <ProviderPicker value={setting.provider} auth={auth} onSelect={select} />
      <button type="button" className="btn" disabled={busy} onClick={next}>계속</button>
    </section>
  );
}
