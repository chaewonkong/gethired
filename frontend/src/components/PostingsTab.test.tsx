import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Job, Posting } from "../api";
import { makeCompany, makePosting, stubIntersectionObserver } from "../test/fixtures";
import { formatTime, PostingsTab } from "./PostingsTab";

const companies = [makeCompany(), makeCompany({ company: "naver", display_name: "네이버" })];
const byId = Object.fromEntries(companies.map((c) => [c.company, c]));

function renderTab(postings: Posting[], props: Partial<Parameters<typeof PostingsTab>[0]> = {}) {
  const onScrape = vi.fn();
  const onToggleBookmark = vi.fn();
  const utils = render(
    <PostingsTab postings={postings} companies={companies} byId={byId} job={null} scraping={false}
                 onScrape={onScrape} onToggleBookmark={onToggleBookmark} {...props} />,
  );
  return { ...utils, onScrape, onToggleBookmark };
}

const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("PostingsTab 목록", () => {
  it("score 내림차순으로 정렬하고 건수를 보여준다", () => {
    renderTab([makePosting({ title: "a", score: 50 }), makePosting({ title: "b", score: 90 }), makePosting({ title: "c", score: 70 })]);
    expect(titles()).toEqual(["b", "c", "a"]);
    expect(screen.getByText("3건")).toBeInTheDocument();
  });

  it("회사 필터", async () => {
    renderTab([makePosting({ title: "toss", company: "toss" }), makePosting({ title: "naver", company: "naver" })]);
    await userEvent.selectOptions(screen.getByDisplayValue("전체 회사"), "naver");
    expect(titles()).toEqual(["naver"]);
  });

  it("등급 필터는 선택 등급 이상만", async () => {
    renderTab([
      makePosting({ title: "s", fit_level: "strong", score: 90 }),
      makePosting({ title: "g", fit_level: "good", score: 80 }),
      makePosting({ title: "t", fit_level: "stretch", score: 70 }),
    ]);
    const level = screen.getByDisplayValue("전체 등급");
    await userEvent.selectOptions(level, "good");
    expect(titles()).toEqual(["s", "g"]);
    await userEvent.selectOptions(level, "strong");
    expect(titles()).toEqual(["s"]);
  });

  it("공고가 없으면 빈 상태 안내", () => {
    renderTab([]);
    expect(screen.getByText(/저장된 공고가 없습니다/)).toBeInTheDocument();
  });

  it("카드의 별 클릭을 상위로 전달한다", async () => {
    const p = makePosting();
    const { onToggleBookmark } = renderTab([p]);
    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    expect(onToggleBookmark).toHaveBeenCalledWith(p);
  });
});

describe("PostingsTab infinite scroll", () => {
  const many = (n: number) => Array.from({ length: n }, (_, i) => makePosting({ title: `p${i}`, score: 1000 - i }));

  it("20건씩 보여주고 sentinel이 보이면 다음 페이지를 붙인다", () => {
    const io = stubIntersectionObserver();
    renderTab(many(45));
    expect(titles()).toHaveLength(20);
    expect(screen.getByText(/20 \/ 45건/)).toBeInTheDocument();

    act(() => io.intersect());
    expect(titles()).toHaveLength(40);

    act(() => io.intersect());
    expect(titles()).toHaveLength(45);
    expect(screen.queryByText(/더 불러오는 중/)).not.toBeInTheDocument();
  });

  it("필터를 바꾸면 처음 20건으로 돌아간다", async () => {
    const io = stubIntersectionObserver();
    renderTab(many(45));
    act(() => io.intersect());
    expect(titles()).toHaveLength(40);

    await userEvent.selectOptions(screen.getByDisplayValue("전체 등급"), "good");
    expect(titles()).toHaveLength(20);
  });

  it("20건 이하면 sentinel이 없다", () => {
    stubIntersectionObserver();
    renderTab(many(20));
    expect(screen.queryByText(/더 불러오는 중/)).not.toBeInTheDocument();
  });
});

describe("PostingsTab 스크래핑", () => {
  const job = (over: Partial<Job> = {}): Job => ({
    job_id: "j1",
    status: "done",
    started_at: "2026-10-09T00:00:00",
    finished_at: "2026-10-09T00:01:00",
    cost_usd: 0.94,
    companies: {
      toss: { status: "done", fetched: 10, new: 5, stored: 3, excluded: 2, deleted: 0, error: null },
      naver: { status: "failed", fetched: 0, new: 0, stored: 0, excluded: 0, deleted: 0, error: "boom" },
    },
    ...over,
  });

  it("버튼을 누르면 onScrape", async () => {
    const { onScrape } = renderTab([]);
    await userEvent.click(screen.getByRole("button", { name: "스크래핑 하기" }));
    expect(onScrape).toHaveBeenCalledOnce();
  });

  it("스크래핑 중이면 버튼 비활성화 + 회사별 진행 표시", () => {
    const running = job({ status: "running", companies: { toss: { status: "running", fetched: 10, new: 4, stored: 0, excluded: 0, deleted: 0, error: null } } });
    renderTab([], { scraping: true, job: running });
    expect(screen.getByRole("button", { name: "스크래핑 중…" })).toBeDisabled();
    expect(screen.getByText(/4건 판정 중/)).toBeInTheDocument();
  });

  it("완료되면 판정·저장 건수, 실패 회사, 비용 요약", () => {
    const { container } = renderTab([], { job: job() });
    const summary = within(container.querySelector(".progress") as HTMLElement);
    expect(summary.getByText("스크래핑 완료")).toBeInTheDocument();
    expect(container.querySelector(".progress")).toHaveTextContent("신규 판정 5건, 저장 3건");
    expect(container.querySelector(".progress")).toHaveTextContent("실패: naver");
    expect(summary.getByText(/\$0\.94 상당/)).toBeInTheDocument();
  });

  it("마지막 스크래핑 시각은 회사들 중 가장 최근", () => {
    const cs = [
      makeCompany({ last_run: { status: "done", started_at: "", finished_at: "2026-10-08T01:00:00Z", error: null, fetched_count: 1 } }),
      makeCompany({ company: "naver", display_name: "네이버", last_run: { status: "done", started_at: "", finished_at: "2026-10-09T01:05:00Z", error: null, fetched_count: 1 } }),
    ];
    renderTab([], { companies: cs });
    expect(screen.getByText(/마지막 스크래핑 2026-10-09 10:05/)).toBeInTheDocument();
  });
});

describe("formatTime", () => {
  it("로컬 시각 YYYY-MM-DD HH:mm", () => {
    expect(formatTime("2026-10-09T15:04:00Z")).toBe("2026-10-10 00:04");
  });
});
