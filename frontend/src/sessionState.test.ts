import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSessionState } from "./sessionState";

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
