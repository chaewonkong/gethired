import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderInRouter } from "../test/renderApp";
import { makePosting } from "../test/fixtures";
import { PostingCard } from "./PostingCard";

function renderCard(over = {}, onToggleBookmark = vi.fn(), onToggleHidden = vi.fn(), onToggleApplied = vi.fn()) {
  const posting = makePosting(over);
  renderInRouter(<PostingCard posting={posting} companyName="토스" onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} onToggleApplied={onToggleApplied} />);
  return { posting, onToggleBookmark, onToggleHidden, onToggleApplied };
}

describe("PostingCard", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-09T23:30:00+09:00"));
  });

  it("수집일은 처음 수집 시각", () => {
    renderCard({ first_seen_at: "2026-10-01T00:00:00+00:00", scraped_at: "2026-10-09T00:00:00+00:00" });
    expect(screen.getByText("수집 2026-10-01")).toBeInTheDocument();
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
    const { container } = renderInRouter(
      <PostingCard posting={makePosting({ gaps: [], tech_stack: [] })} companyName="토스" onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={vi.fn()} />,
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

describe("PostingCard 상세 이동", () => {
  const setup = (over = {}) => {
    const posting = makePosting(over);
    const onToggleBookmark = vi.fn();
    const onToggleHidden = vi.fn();
    const onToggleApplied = vi.fn();
    const utils = renderInRouter(
      <PostingCard posting={posting} companyName="토스" visible={40} onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} onToggleApplied={onToggleApplied} />,
      { entries: ["/bookmarks"] },
    );
    return { ...utils, posting, onToggleBookmark, onToggleHidden, onToggleApplied };
  };

  it("카드를 누르면 위치를 저장하고 /postings/:id로 이동한다", async () => {
    window.scrollY = 1234;
    const { location, posting } = setup({ id: 7 });
    await userEvent.click(screen.getByText(posting.summary));
    expect(location().pathname).toBe("/postings/7");
    expect(JSON.parse(sessionStorage.getItem("listPosition:/bookmarks")!)).toEqual({ scrollY: 1234, visible: 40 });
    window.scrollY = 0;
  });

  it("제목을 눌러도 이동한다", async () => {
    const { location, posting } = setup({ id: 8 });
    await userEvent.click(screen.getByRole("heading", { name: posting.title }));
    expect(location().pathname).toBe("/postings/8");
  });

  it("카드에 포커스하고 Enter를 누르면 이동한다", async () => {
    const { location, posting } = setup({ id: 9 });
    screen.getByRole("link", { name: posting.title }).focus();
    await userEvent.keyboard("{Enter}");
    expect(location().pathname).toBe("/postings/9");
  });

  it("별·숨김 클릭은 이동하지 않고 콜백만 호출한다", async () => {
    const { location, posting, onToggleBookmark, onToggleHidden } = setup();
    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    await userEvent.click(screen.getByRole("button", { name: "숨김" }));
    expect(onToggleBookmark).toHaveBeenCalledWith(posting);
    expect(onToggleHidden).toHaveBeenCalledWith(posting);
    expect(location().pathname).toBe("/bookmarks");
    expect(sessionStorage.getItem("listPosition:/bookmarks")).toBeNull();
  });
});

describe("PostingCard 지원완료", () => {
  const applied = { applied_at: "2026-10-20T03:00:00+00:00", stage: null };
  const closed = { deleted_at: "2026-10-25T00:00:00+00:00" };

  it("미지원 공고는 빈 체크, 누르면 핸들러에 공고를 넘기고 이동하지 않는다", async () => {
    const posting = makePosting();
    const onToggleApplied = vi.fn();
    const { location } = renderInRouter(
      <PostingCard posting={posting} companyName="토스" onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={onToggleApplied} />,
      { entries: ["/bookmarks"] },
    );
    const check = screen.getByRole("button", { name: "지원완료" });
    expect(check).toHaveAttribute("aria-pressed", "false");
    expect(check).not.toHaveClass("on");
    expect(check).toBeEnabled();
    await userEvent.click(check);
    expect(onToggleApplied).toHaveBeenCalledWith(posting);
    expect(location().pathname).toBe("/bookmarks");
    expect(screen.queryByText(/지원완료 ·/)).toBeNull();
  });

  it("지원완료 공고는 채워진 체크와 로컬 날짜 기준 지원일", () => {
    renderCard({ application: { applied_at: "2026-10-20T23:30:00+00:00", stage: null } });
    const check = screen.getByRole("button", { name: "지원완료 해제" });
    expect(check).toHaveAttribute("aria-pressed", "true");
    expect(check).toHaveClass("on");
    expect(screen.getByText("지원완료 · 2026-10-21")).toHaveClass("applied-at");
  });

  it("단계가 있으면 라벨 자리에 단계", () => {
    renderCard({ application: { ...applied, stage: "서류합격" } });
    expect(screen.getByText("서류합격 · 2026-10-20")).toBeInTheDocument();
  });

  it("마감된 지원완료 공고는 마감 배지, 별·숨김은 disabled, 체크는 해제 가능", async () => {
    const { onToggleBookmark, onToggleHidden, onToggleApplied } = renderCard({ ...closed, application: applied, deadline: "2026-10-30" });
    expect(screen.getByText("마감")).toHaveClass("deadline", "closed");
    expect(screen.queryByText(/마감 2026-10-30/)).toBeNull();
    const star = screen.getByRole("button", { name: "북마크" });
    const eye = screen.getByRole("button", { name: "숨김" });
    expect(star).toBeDisabled();
    expect(eye).toBeDisabled();
    await userEvent.click(star);
    await userEvent.click(eye);
    expect(onToggleBookmark).not.toHaveBeenCalled();
    expect(onToggleHidden).not.toHaveBeenCalled();
    const check = screen.getByRole("button", { name: "지원완료 해제" });
    expect(check).toBeEnabled();
    await userEvent.click(check);
    expect(onToggleApplied).toHaveBeenCalled();
  });

  it("마감됐는데 지원완료가 아니면 체크도 disabled", async () => {
    const { onToggleApplied } = renderCard(closed);
    const check = screen.getByRole("button", { name: "지원완료" });
    expect(check).toBeDisabled();
    await userEvent.click(check);
    expect(onToggleApplied).not.toHaveBeenCalled();
  });
});
