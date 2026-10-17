import { useEffect } from "react";
import { AuthStatus, Provider } from "../api";
import { ProviderPicker } from "./ProviderPicker";

interface Props {
  value: Provider;
  auth: AuthStatus | null;
  disabled: boolean;
  onSelect: (provider: Provider) => void;
  onClose: () => void;
}

export function ProviderModal({ value, auth, disabled, onSelect, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="provider-modal-title">
        <div className="modal-head">
          <h2 id="provider-modal-title">AI 선택</h2>
          <button type="button" className="modal-close" aria-label="AI 선택 창 닫기" onClick={onClose}>×</button>
        </div>
        <p className="meta">고르면 바로 저장되고 다음 스크래핑부터 적용됩니다. 로그인은 터미널에서 합니다.</p>
        <ProviderPicker value={value} auth={auth} disabled={disabled} onSelect={onSelect} />
      </div>
    </div>
  );
}
