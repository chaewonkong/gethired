import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderInRouter } from "../test/renderApp";
import { makeCompany, makePosting } from "../test/fixtures";
import { HiddenTab } from "./HiddenTab";

const byId = { toss: makeCompany() };
const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("HiddenTab", () => {
  it("숨긴 공고만 score 내림차순으로, 북마크 여부와 무관", () => {
    renderInRouter(
      <HiddenTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={vi.fn()} postings={[
        makePosting({ title: "low", score: 40, hidden: true }),
        makePosting({ title: "none", score: 99 }),
        makePosting({ title: "high", score: 80, hidden: true, bookmarked: true }),
      ]} />,
    );
    expect(titles()).toEqual(["high", "low"]);
  });

  it("숨긴 공고가 없으면 빈 상태 안내", () => {
    renderInRouter(<HiddenTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={vi.fn()} postings={[makePosting()]} />);
    expect(screen.getByText(/숨긴 공고가 없습니다/)).toBeInTheDocument();
  });

  it("눈 버튼을 누르면 해제 핸들러 호출", async () => {
    const p = makePosting({ hidden: true });
    const onToggleHidden = vi.fn();
    renderInRouter(<HiddenTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={onToggleHidden} onToggleApplied={vi.fn()} postings={[p]} />);
    await userEvent.click(screen.getByRole("button", { name: "숨김 해제" }));
    expect(onToggleHidden).toHaveBeenCalledWith(p);
  });
});
