import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Toast } from "./Toast";

describe("Toast", () => {
  it("2초 뒤 onClose, 다시 렌더돼도 타이머는 유지", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    const toast = { id: 1, text: "done", kind: "ok" as const };
    const { rerender } = render(<Toast toast={toast} onClose={onClose} />);
    expect(screen.getByRole("status")).toHaveTextContent("done");
    act(() => vi.advanceTimersByTime(1500));
    rerender(<Toast toast={toast} onClose={onClose} />);
    expect(onClose).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(500));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
