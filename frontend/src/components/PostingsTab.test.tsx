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
  const onToggleHidden = vi.fn();
  const utils = render(
    <PostingsTab postings={postings} companies={companies} byId={byId} job={null} scraping={false}
                 onScrape={onScrape} onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} {...props} />,
  );
  return { ...utils, onScrape, onToggleBookmark, onToggleHidden };
}

const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("PostingsTab 목록", () => {
  it("score 내림차순으로 정렬하고 건수를 보여준다", () => {
    renderTab([makePosting({ title: "a", score: 50 }), makePosting({ title: "b", score: 90 }), makePosting({ title: "c", score: 70 })]);
    expect(titles()).toEqual(["b", "c", "a"]);
    expect(screen.getByText("3건")).toBeInTheDocument();
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

  it("정렬: 최신순·오래된순은 처음 수집 시각 기준, 같으면 score순", async () => {
    renderTab([
      makePosting({ title: "old", score: 90, first_seen_at: "2026-10-01T00:00:00+00:00" }),
      makePosting({ title: "new-lo", score: 50, first_seen_at: "2026-10-05T00:00:00+00:00" }),
      makePosting({ title: "new-hi", score: 80, first_seen_at: "2026-10-05T00:00:00+00:00" }),
    ]);
    expect(titles()).toEqual(["old", "new-hi", "new-lo"]);
    const sort = screen.getByRole("combobox", { name: "정렬" });
    await userEvent.selectOptions(sort, "newest");
    expect(titles()).toEqual(["new-hi", "new-lo", "old"]);
    await userEvent.selectOptions(sort, "oldest");
    expect(titles()).toEqual(["old", "new-hi", "new-lo"]);
    expect(sessionStorage.getItem("postings.sort")).toBe(JSON.stringify("oldest"));
  });

  it("저장된 정렬로 시작한다", () => {
    sessionStorage.setItem("postings.sort", JSON.stringify("newest"));
    renderTab([
      makePosting({ title: "old", score: 90, first_seen_at: "2026-10-01T00:00:00+00:00" }),
      makePosting({ title: "new", score: 50, first_seen_at: "2026-10-05T00:00:00+00:00" }),
    ]);
    expect(titles()).toEqual(["new", "old"]);
    expect(screen.getByDisplayValue("최신순")).toBeInTheDocument();
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

const companyTrigger = () => screen.getByRole("button", { name: /^회사 필터/ });
const openCompanyFilter = () => userEvent.click(companyTrigger());
const companyBox = (name: RegExp) => screen.getByRole("checkbox", { name });

describe("PostingsTab 회사 필터", () => {
  const posts = () => [
    makePosting({ title: "toss-strong", company: "toss", fit_level: "strong", score: 90 }),
    makePosting({ title: "naver-strong", company: "naver", fit_level: "strong", score: 80 }),
    makePosting({ title: "toss-stretch", company: "toss", fit_level: "stretch", score: 50 }),
  ];

  it("처음에는 전체 회사가 선택되어 전체 공고가 보인다", () => {
    renderTab(posts());
    expect(companyTrigger()).toHaveTextContent("전체 회사");
    expect(titles()).toEqual(["toss-strong", "naver-strong", "toss-stretch"]);
  });

  it("해제한 회사는 빠지고 다시 선택하면 돌아온다", async () => {
    renderTab(posts());
    await openCompanyFilter();
    await userEvent.click(companyBox(/토스/));
    expect(titles()).toEqual(["naver-strong"]);
    await userEvent.click(companyBox(/토스/));
    expect(titles()).toEqual(["toss-strong", "naver-strong", "toss-stretch"]);
  });

  it("등급 필터와 AND로 적용되고 건수에 반영된다", async () => {
    renderTab(posts());
    await userEvent.selectOptions(screen.getByDisplayValue("전체 등급"), "good");
    await openCompanyFilter();
    await userEvent.click(companyBox(/네이버/));
    expect(titles()).toEqual(["toss-strong"]);
    expect(screen.getByText("1건")).toBeInTheDocument();
  });

  it("회사별 건수는 등급 필터를 반영하고 숨긴 공고를 제외한다", async () => {
    renderTab([...posts(), makePosting({ title: "toss-hidden", company: "toss", hidden: true })]);
    await openCompanyFilter();
    expect(companyBox(/토스/)).toHaveAccessibleName("토스 2");
    expect(companyBox(/네이버/)).toHaveAccessibleName("네이버 1");

    await userEvent.selectOptions(screen.getByDisplayValue("전체 등급"), "strong");
    await openCompanyFilter();
    expect(companyBox(/토스/)).toHaveAccessibleName("토스 1");
  });

  it("전체 끄기면 empty view, 전체 켜기면 복귀", async () => {
    renderTab(posts());
    await openCompanyFilter();
    await userEvent.click(screen.getByRole("button", { name: "전체 끄기" }));
    expect(titles()).toEqual([]);
    expect(screen.getByText(/선택된 회사가 없습니다/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "전체 켜기" }));
    expect(titles()).toHaveLength(3);
  });

  it("선택은 sessionStorage에 저장되어 다시 마운트해도 유지된다", async () => {
    const { unmount } = renderTab(posts());
    await userEvent.selectOptions(screen.getByDisplayValue("전체 등급"), "strong");
    await openCompanyFilter();
    await userEvent.click(companyBox(/네이버/));
    unmount();

    renderTab(posts());
    expect(titles()).toEqual(["toss-strong"]);
    expect(screen.getByDisplayValue("strong만")).toBeInTheDocument();
    expect(companyTrigger()).toHaveTextContent("토스");
  });

  it("세션 중 새로 추가된 회사는 선택된 상태로 보인다", () => {
    sessionStorage.setItem("postings.excludedCompanies", JSON.stringify(["naver"]));
    const kakao = makeCompany({ company: "kakao", display_name: "카카오" });
    renderTab([...posts(), makePosting({ title: "kakao", company: "kakao", score: 60 })], {
      companies: [...companies, kakao],
      byId: { ...byId, kakao },
    });
    expect(titles()).toEqual(["toss-strong", "kakao", "toss-stretch"]);
  });

  it("등록되지 않은 회사의 공고는 보이지 않고, 전체 끄기 시 empty view", async () => {
    renderTab([...posts(), makePosting({ title: "orphan", company: "line", score: 99 })]);
    expect(titles()).toEqual(["toss-strong", "naver-strong", "toss-stretch"]);
    await openCompanyFilter();
    await userEvent.click(screen.getByRole("button", { name: "전체 끄기" }));
    expect(titles()).toEqual([]);
    expect(screen.getByText(/선택된 회사가 없습니다/)).toBeInTheDocument();
  });

  it("저장된 등급이 Object 프로토타입 키여도 기본값", () => {
    sessionStorage.setItem("postings.minLevel", JSON.stringify("toString"));
    renderTab(posts());
    expect(titles()).toHaveLength(3);
    expect(screen.getByDisplayValue("전체 등급")).toBeInTheDocument();
  });

  it("저장값이 깨져 있으면 기본값", () => {
    sessionStorage.setItem("postings.excludedCompanies", "{oops");
    sessionStorage.setItem("postings.minLevel", JSON.stringify("bogus"));
    sessionStorage.setItem("postings.sort", JSON.stringify("bogus"));
    renderTab(posts());
    expect(titles()).toHaveLength(3);
    expect(screen.getByDisplayValue("전체 등급")).toBeInTheDocument();
    expect(screen.getByDisplayValue("적합도순")).toBeInTheDocument();
  });
});

describe("PostingsTab 숨김", () => {
  it("숨긴 공고는 목록과 건수에서 빠진다", () => {
    renderTab([makePosting({ title: "a" }), makePosting({ title: "h", hidden: true, score: 99 })]);
    expect(titles()).toEqual(["a"]);
    expect(screen.getByText("1건")).toBeInTheDocument();
  });

  it("카드의 숨김 클릭을 상위로 전달한다", async () => {
    const p = makePosting();
    const { onToggleHidden } = renderTab([p]);
    await userEvent.click(screen.getByRole("button", { name: "숨김" }));
    expect(onToggleHidden).toHaveBeenCalledWith(p);
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

  it("스크롤 중 공고를 숨기거나 북마크해도 페이지가 줄어들지 않는다", () => {
    const io = stubIntersectionObserver();
    const posts = many(45);
    const { rerender } = renderTab(posts);
    act(() => io.intersect());
    expect(titles()).toHaveLength(40);

    const next = posts.map((p, i) => (i === 0 ? { ...p, hidden: true } : i === 1 ? { ...p, bookmarked: true } : p));
    rerender(
      <PostingsTab postings={next} companies={companies} byId={byId} job={null} scraping={false}
                   onScrape={vi.fn()} onToggleBookmark={vi.fn()} onToggleHidden={vi.fn()} />,
    );
    expect(titles()).toHaveLength(40);
  });

  it("회사 필터를 바꿔도 처음 20건으로 돌아간다", async () => {
    const io = stubIntersectionObserver();
    renderTab(many(45));
    act(() => io.intersect());
    expect(titles()).toHaveLength(40);

    await openCompanyFilter();
    await userEvent.click(companyBox(/네이버/));
    expect(titles()).toHaveLength(20);
  });

  it("정렬을 바꿔도 처음 20건으로 돌아간다", async () => {
    const io = stubIntersectionObserver();
    renderTab(many(45));
    act(() => io.intersect());
    expect(titles()).toHaveLength(40);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "정렬" }), "newest");
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
