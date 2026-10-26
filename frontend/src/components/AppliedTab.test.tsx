import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderInRouter } from "../test/renderApp";
import { makeCompany, makePosting } from "../test/fixtures";
import { AppliedTab } from "./AppliedTab";

const byId = { toss: makeCompany() };
const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);
const applied = { applied_at: "2026-10-20T03:00:00+00:00", stage: null };

describe("AppliedTab", () => {
  it("받은 순서 그대로 카드를 그리고 지원일을 보여준다", () => {
    renderInRouter(
      <AppliedTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={vi.fn()} postings={[
        makePosting({ title: "first", score: 10, application: applied }),
        makePosting({ title: "second", score: 99, application: applied }),
      ]} />,
    );
    expect(titles()).toEqual(["first", "second"]);
    expect(screen.getAllByText("지원완료 · 2026-10-20")).toHaveLength(2);
  });

  it("지원한 공고가 없으면 빈 상태 안내", () => {
    renderInRouter(<AppliedTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={vi.fn()} postings={[]} />);
    expect(screen.getByText(/지원한 공고가 없습니다/)).toBeInTheDocument();
  });

  it("체크를 누르면 해제 핸들러 호출", async () => {
    const p = makePosting({ application: applied });
    const onToggleApplied = vi.fn();
    renderInRouter(<AppliedTab byId={byId} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} onToggleApplied={onToggleApplied} postings={[p]} />);
    await userEvent.click(screen.getByRole("button", { name: "지원완료 해제" }));
    expect(onToggleApplied).toHaveBeenCalledWith(p);
  });
});
