import { useEffect, useState } from "react";

/** 브라우저 세션 동안 유지되는 state. 저장소 접근·파싱 실패 시 기본값 */
export function useSessionState<T>(key: string, initial: T, parse: (raw: unknown) => T | null): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = sessionStorage.getItem(key);
      return raw === null ? initial : (parse(JSON.parse(raw)) ?? initial);
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      // 저장 실패 시 이번 렌더 동안만 유지
    }
  }, [key, value]);

  return [value, setValue];
}
