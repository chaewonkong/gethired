import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ScrapeRun } from "../api";
import { makeCompany } from "../test/fixtures";
import { CompaniesTab } from "./CompaniesTab";

const run = (over: Partial<ScrapeRun>): ScrapeRun => ({
  status: "done", started_at: "2026-10-09T00:00:00Z", finished_at: "2026-10-09T00:01:00Z", error: null, fetched_count: 12, ...over,
});

describe("CompaniesTab", () => {
  it("회사별 마지막 실행 상태를 보여준다", () => {
    render(
      <CompaniesTab onToggleInterest={() => {}} companies={[
        makeCompany({ company: "a", display_name: "A사", last_run: run({}) }),
        makeCompany({ company: "b", display_name: "B사", last_run: run({ status: "failed", error: "timeout" }) }),
        makeCompany({ company: "c", display_name: "C사", last_run: run({ status: "auth_required" }) }),
        makeCompany({ company: "d", display_name: "D사", last_run: run({ status: "running", finished_at: null }) }),
        makeCompany({ company: "e", display_name: "E사", last_run: null }),
      ]} />,
    );
    expect(screen.getByText("성공 · 12건")).toHaveClass("ok");
    expect(screen.getByText("실패 · timeout")).toHaveClass("fail");
    expect(screen.getByText("로그인 필요")).toHaveClass("fail");
    expect(screen.getByText("진행 중")).toBeInTheDocument();
    expect(screen.getByText("기록 없음")).toBeInTheDocument();
    expect(screen.getAllByText("2026-10-09 09:01")).toHaveLength(3);
  });

  it("채용 사이트 링크는 프로토콜 없이 표시", () => {
    render(<CompaniesTab onToggleInterest={() => {}} companies={[makeCompany({ careers_url: "https://toss.im/career" })]} />);
    expect(screen.getByRole("link", { name: "toss.im/career" })).toHaveAttribute("href", "https://toss.im/career");
  });

  it("관심회사는 칠해진 별, 누르면 onToggleInterest", async () => {
    const onToggle = vi.fn();
    const naver = makeCompany({ company: "naver", display_name: "네이버", interested: false });
    render(<CompaniesTab onToggleInterest={onToggle} companies={[makeCompany(), naver]} />);
    expect(screen.getByRole("button", { name: "토스 관심회사 해제" })).toHaveClass("on");
    expect(screen.getByRole("button", { name: "네이버 관심회사 추가" })).not.toHaveClass("on");
    await userEvent.click(screen.getByRole("button", { name: "네이버 관심회사 추가" }));
    expect(onToggle).toHaveBeenCalledWith(naver);
  });
});
