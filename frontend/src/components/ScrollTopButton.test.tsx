import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScrollTopButton } from "./ScrollTopButton";

function scrollTo(y: number) {
  act(() => {
    window.scrollY = y;
    fireEvent.scroll(window);
  });
}

describe("ScrollTopButton", () => {
  it("600px 넘게 스크롤하면 보이고, 다시 올라오면 숨는다", () => {
    render(<ScrollTopButton />);
    const btn = screen.getByRole("button", { name: "맨 위로" });
    expect(btn).not.toHaveClass("show");
    expect(btn).toHaveAttribute("tabindex", "-1");

    scrollTo(601);
    expect(btn).toHaveClass("show");
    expect(btn).toHaveAttribute("tabindex", "0");

    scrollTo(100);
    expect(btn).not.toHaveClass("show");
  });

  it("누르면 최상단으로 부드럽게 스크롤", () => {
    const spy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    render(<ScrollTopButton />);
    scrollTo(1000);
    fireEvent.click(screen.getByRole("button", { name: "맨 위로" }));
    expect(spy).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
  });
});
