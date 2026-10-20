import { useEffect, useRef, useState } from "react";
import { NavigationType, useNavigationType } from "react-router-dom";

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

/** 목록에서 상세로 가기 직전의 위치. visible은 무한 스크롤로 불러온 건수 (페이지 없는 목록은 null) */
export interface ListPosition {
  scrollY: number;
  visible: number | null;
}

const positionKey = (path: string) => `listPosition:${path}`;

export function saveListPosition(path: string, pos: ListPosition) {
  try {
    sessionStorage.setItem(positionKey(path), JSON.stringify(pos));
  } catch {
    // 저장 실패 시 복원하지 않는다
  }
}

function readListPosition(path: string): ListPosition | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(positionKey(path)) ?? "null");
    if (typeof raw?.scrollY !== "number") return null;
    return { scrollY: raw.scrollY, visible: typeof raw.visible === "number" ? raw.visible : null };
  } catch {
    return null;
  }
}

/** 뒤로가기(POP)로 들어오면 저장된 위치를 돌려주고 ready가 된 렌더 뒤 그 위치로 스크롤한다. 그 외 진입은 맨 위 */
export function useListPosition(path: string, ready: boolean): ListPosition | null {
  const pop = useNavigationType() === NavigationType.Pop;
  const [saved] = useState(() => (pop ? readListPosition(path) : null));
  const done = useRef(false);

  useEffect(() => {
    if (done.current || (saved && !ready)) return;
    done.current = true;
    window.scrollTo(0, saved?.scrollY ?? 0);
  }, [saved, ready]);

  return saved;
}
