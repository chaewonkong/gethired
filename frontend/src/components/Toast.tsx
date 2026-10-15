import { useEffect, useRef } from "react";

export const TOAST_MS = 2000;

export interface ToastMessage {
  id: number;
  text: string;
  kind: "ok" | "error";
}

/** TOAST_MS 뒤 자동으로 닫힌다. 같은 id 동안 타이머는 한 번만 */
export function Toast({ toast, onClose }: { toast: ToastMessage; onClose: () => void }) {
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const t = setTimeout(() => close.current(), TOAST_MS);
    return () => clearTimeout(t);
  }, [toast.id]);

  return (
    <div className={`toast ${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
      <span>{toast.text}</span>
      <button type="button" aria-label="닫기" onClick={onClose}>×</button>
    </div>
  );
}
