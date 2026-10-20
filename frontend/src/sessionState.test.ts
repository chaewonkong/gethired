import { act, renderHook } from "@testing-library/react";
import { createElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { saveListPosition, useListPosition, useSessionState } from "./sessionState";

const strings = (raw: unknown) => (Array.isArray(raw) && raw.every((x) => typeof x === "string") ? raw : null);

describe("useSessionState", () => {
  it("저장값이 없으면 기본값", () => {
    const { result } = renderHook(() => useSessionState("k", ["a"], strings));
    expect(result.current[0]).toEqual(["a"]);
  });

  it("바꾼 값은 sessionStorage에 저장되고 다시 마운트하면 복원된다", () => {
    const first = renderHook(() => useSessionState<string[]>("k", [], strings));
    act(() => first.result.current[1](["toss"]));
    expect(first.result.current[0]).toEqual(["toss"]);
    expect(JSON.parse(sessionStorage.getItem("k")!)).toEqual(["toss"]);
    first.unmount();

    const second = renderHook(() => useSessionState<string[]>("k", [], strings));
    expect(second.result.current[0]).toEqual(["toss"]);
  });

  it("깨진 JSON이면 기본값", () => {
    sessionStorage.setItem("k", "{oops");
    const { result } = renderHook(() => useSessionState("k", ["d"], strings));
    expect(result.current[0]).toEqual(["d"]);
  });

  it("형식이 맞지 않으면 기본값", () => {
    sessionStorage.setItem("k", JSON.stringify({ not: "array" }));
    const { result } = renderHook(() => useSessionState("k", ["d"], strings));
    expect(result.current[0]).toEqual(["d"]);
  });

  it("저장소 접근이 실패해도 기본값으로 동작하고 값은 바뀐다", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const { result } = renderHook(() => useSessionState<string[]>("k", ["d"], strings));
    expect(result.current[0]).toEqual(["d"]);
    act(() => result.current[1](["x"]));
    expect(result.current[0]).toEqual(["x"]);
  });
});

describe("목록 위치", () => {
  const pop = ({ children }: { children: ReactNode }) => createElement(MemoryRouter, { initialEntries: ["/"] }, children);

  it("저장한 위치를 POP 진입에서 돌려주고, ready가 되면 그 위치로 스크롤한다", () => {
    const scrollTo = vi.spyOn(window, "scrollTo");
    saveListPosition("/", { scrollY: 500, visible: 60 });
    const { result, rerender } = renderHook(({ ready }) => useListPosition("/", ready), { wrapper: pop, initialProps: { ready: false } });
    expect(result.current).toEqual({ scrollY: 500, visible: 60 });
    expect(scrollTo).not.toHaveBeenCalled();

    rerender({ ready: true });
    expect(scrollTo).toHaveBeenCalledWith(0, 500);
    rerender({ ready: false });
    rerender({ ready: true });
    expect(scrollTo).toHaveBeenCalledTimes(1);
  });

  it("경로별로 따로 저장하고 visible이 없으면 null", () => {
    saveListPosition("/bookmarks", { scrollY: 10, visible: null });
    expect(renderHook(() => useListPosition("/bookmarks", true), { wrapper: pop }).result.current).toEqual({ scrollY: 10, visible: null });
    expect(renderHook(() => useListPosition("/hidden", true), { wrapper: pop }).result.current).toBeNull();
  });

  it("저장값이 없거나 깨졌으면 null이고 맨 위로", () => {
    const scrollTo = vi.spyOn(window, "scrollTo");
    sessionStorage.setItem("listPosition:/", "{oops");
    expect(renderHook(() => useListPosition("/", false), { wrapper: pop }).result.current).toBeNull();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });
});
