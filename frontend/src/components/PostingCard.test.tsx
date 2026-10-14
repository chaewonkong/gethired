import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makePosting } from "../test/fixtures";
import { PostingCard } from "./PostingCard";

function renderCard(over = {}, onToggleBookmark = vi.fn(), onToggleHidden = vi.fn()) {
  const posting = makePosting(over);
  render(<PostingCard posting={posting} companyName="토스" onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} />);
  return { posting, onToggleBookmark, onToggleHidden };
}

describe("PostingCard", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-09T23:30:00+09:00"));
  });

  it("마감일이 없으면 상시 채용", () => {
    renderCard({ deadline: null });
    expect(screen.getByText("상시 채용")).toBeInTheDocument();
  });

  it("마감 7일 이내면 로컬 날짜 기준 D-day를 강조한다", () => {
    renderCard({ deadline: "2026-10-12" });
    const el = screen.getByText("마감 2026-10-12 (D-3)");
    expect(el).toHaveClass("soon");
  });

  it("마감 당일은 D-0", () => {
    renderCard({ deadline: "2026-10-09" });
    expect(screen.getByText("마감 2026-10-09 (D-0)")).toBeInTheDocument();
  });

  it("마감이 7일보다 남으면 D-day 없이 날짜만", () => {
    renderCard({ deadline: "2026-10-17" });
    const el = screen.getByText("마감 2026-10-17");
    expect(el).not.toHaveClass("soon");
  });

  it("공고 정보와 지원 링크를 보여준다", () => {
    renderCard({ title: "Matchmaking Engineer", fit_level: "strong", score: 91, tech_stack: ["Go", "Redis"], gaps: ["Kotlin"] });
    expect(screen.getByRole("heading", { name: "Matchmaking Engineer" })).toBeInTheDocument();
    expect(screen.getByText("strong · 91")).toHaveClass("level", "strong");
    expect(screen.getByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("Kotlin")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /지원하기/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("gaps·tech_stack이 비면 해당 영역을 그리지 않는다", () => {
    const { container } = render(
      <PostingCard posting={makePosting({ gaps: [], tech_stack: [] })} companyName="토스" onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} />,
    );
    expect(container.querySelector(".gaps")).toBeNull();
    expect(container.querySelector(".chips")).toBeNull();
  });
});

describe("PostingCard 북마크 별", () => {
  it("북마크 안 된 공고는 빈 별, 누르면 핸들러에 공고를 넘긴다", async () => {
    const { posting, onToggleBookmark } = renderCard({ bookmarked: false });
    const star = screen.getByRole("button", { name: "북마크" });
    expect(star).toHaveAttribute("aria-pressed", "false");
    expect(star).not.toHaveClass("on");
    await userEvent.click(star);
    expect(onToggleBookmark).toHaveBeenCalledWith(posting);
  });

  it("북마크된 공고는 채워진 별", () => {
    renderCard({ bookmarked: true });
    const star = screen.getByRole("button", { name: "북마크 해제" });
    expect(star).toHaveAttribute("aria-pressed", "true");
    expect(star).toHaveClass("on");
  });
});

describe("PostingCard 숨김 버튼", () => {
  it("숨기지 않은 공고는 꺼진 눈 버튼, 누르면 핸들러에 공고를 넘긴다", async () => {
    const { posting, onToggleHidden } = renderCard({ hidden: false });
    const eye = screen.getByRole("button", { name: "숨김" });
    expect(eye).toHaveAttribute("aria-pressed", "false");
    expect(eye).not.toHaveClass("on");
    await userEvent.click(eye);
    expect(onToggleHidden).toHaveBeenCalledWith(posting);
  });

  it("숨긴 공고는 켜진 눈 버튼", () => {
    renderCard({ hidden: true });
    const eye = screen.getByRole("button", { name: "숨김 해제" });
    expect(eye).toHaveAttribute("aria-pressed", "true");
    expect(eye).toHaveClass("on");
  });
});
