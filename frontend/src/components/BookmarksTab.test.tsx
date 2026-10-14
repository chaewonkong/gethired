import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeCompany, makePosting } from "../test/fixtures";
import { BookmarksTab } from "./BookmarksTab";

const byId = { toss: makeCompany() };
const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("BookmarksTab", () => {
  it("북마크한 공고만 score 내림차순으로", () => {
    render(
      <BookmarksTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} postings={[
        makePosting({ title: "low", score: 40, bookmarked: true }),
        makePosting({ title: "none", score: 99, bookmarked: false }),
        makePosting({ title: "high", score: 80, bookmarked: true }),
      ]} />,
    );
    expect(titles()).toEqual(["high", "low"]);
  });

  it("숨긴 공고는 북마크돼 있어도 빠진다", () => {
    render(
      <BookmarksTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} postings={[
        makePosting({ title: "shown", bookmarked: true }),
        makePosting({ title: "hidden", bookmarked: true, hidden: true, score: 99 }),
      ]} />,
    );
    expect(titles()).toEqual(["shown"]);
  });

  it("북마크가 없으면 빈 상태 안내", () => {
    render(<BookmarksTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} postings={[makePosting()]} />);
    expect(screen.getByText(/북마크한 공고가 없습니다/)).toBeInTheDocument();
  });

  it("별을 누르면 해제 핸들러 호출", async () => {
    const p = makePosting({ bookmarked: true });
    const onToggleBookmark = vi.fn();
    render(<BookmarksTab byId={byId} onToggleBookmark={onToggleBookmark} onToggleHidden={vi.fn()} postings={[p]} />);
    await userEvent.click(screen.getByRole("button", { name: "북마크 해제" }));
    expect(onToggleBookmark).toHaveBeenCalledWith(p);
  });
});
