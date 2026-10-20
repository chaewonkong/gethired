import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Feedback, Posting, PostingDetail as Detail } from "../api";
import { makeCompany, makeDetail, makePosting } from "../test/fixtures";
import { renderInRouter } from "../test/renderApp";
import { PostingDetail } from "./PostingDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type Handler = () => Response | Promise<Response>;

function stubApi(detail: Detail | null, feedback?: Handler) {
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (detail && key === `GET /api/postings/${detail.id}`) return json(detail);
    if (detail && key === `POST /api/postings/${detail.id}/feedback` && feedback) return feedback();
    return json({ detail: "posting not found" }, 404);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

interface Opts {
  postings?: Posting[];
  loginRequired?: boolean;
  entries?: string[];
}

function renderDetail({ postings = [], loginRequired = false, entries = ["/postings/1"] }: Opts = {}) {
  const props = {
    postings,
    byId: { toss: makeCompany() },
    onToggleBookmark: vi.fn(async () => true),
    onToggleHidden: vi.fn(async () => true),
    onRequireLogin: vi.fn(),
    onToast: vi.fn(),
  };
  const ui = (login: boolean) => <PostingDetail {...props} loginRequired={login} />;
  const utils = renderInRouter(ui(loginRequired), { entries, route: "/postings/:id" });
  return { ...utils, ...props, setLoginRequired: (v: boolean) => utils.rerender(ui(v)) };
}

const feedback = (over: Partial<Feedback> = {}): Feedback => ({ items: ["경력: Redis 매칭 큐 설계 강조", "성과: 지연 수치화"], created_at: "2026-10-20T00:00:00+00:00", current: true, ...over });
const button = () => screen.queryByRole("button", { name: /피드백 생성|생성 중/ });

describe("PostingDetail", () => {
  it("헤더·공고·정합성을 그리고 본문은 접혀 있다", async () => {
    stubApi(makeDetail({
      id: 1, title: "Matchmaking Engineer", fit_level: "strong", score: 70, description: "원문 본문",
      requirements: [{ text: "Go 3년", fit: "met" }, { text: "Kotlin", fit: "unmet" }, { text: "옛 행", fit: null }],
      preferred: [{ text: "Redis", fit: "partial" }],
    }));
    renderDetail();
    expect(await screen.findByRole("heading", { level: 2, name: "Matchmaking Engineer" })).toBeInTheDocument();
    expect(screen.getByText("strong · 70")).toBeInTheDocument();
    expect(screen.getByText("토스")).toBeInTheDocument();

    // 요건 표는 정합성 섹션에, 항목마다 충족 표시
    const reqs = screen.getByRole("table", { name: "자격요건" });
    expect(reqs.closest("section")).toHaveTextContent("정합성");
    const rows = within(reqs).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Go 3년")).toBeInTheDocument();
    expect(within(rows[0]).getByLabelText("충족")).toHaveTextContent("✓");
    expect(within(rows[0]).getByLabelText("충족")).toHaveClass("met");
    expect(within(rows[1]).getByLabelText("미충족")).toHaveTextContent("✗");
    expect(within(rows[1]).getByLabelText("미충족")).toHaveClass("unmet");
    expect(within(rows[2]).getByLabelText("판정 없음")).toHaveTextContent("–");
    const pref = screen.getByRole("table", { name: "우대사항" });
    expect(within(pref).getByText("Redis")).toBeInTheDocument();
    expect(within(pref).getByLabelText("부분 충족")).toHaveClass("partial");
    expect(screen.getByRole("link", { name: /지원하기/ })).toHaveAttribute("target", "_blank");

    const bars = screen.getAllByRole("meter");
    expect(bars).toHaveLength(4);
    expect(screen.getByText("30/35")).toBeInTheDocument();
    expect(screen.getByText("5/10")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "핵심 기술" }).firstElementChild).toHaveStyle({ width: `${(30 / 35) * 100}%` });

    const body = screen.getByText("공고 본문").closest("details")!;
    expect(body).not.toHaveAttribute("open");
    expect(within(body).getByText("원문 본문")).toBeInTheDocument();
  });

  it("description이 null이면 본문 영역이 없다", async () => {
    stubApi(makeDetail({ id: 1, description: null }));
    renderDetail();
    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByText("공고 본문")).not.toBeInTheDocument();
  });

  it("breakdown이 null이면 재판정 안내", async () => {
    stubApi(makeDetail({ id: 1, breakdown: null }));
    renderDetail();
    expect(await screen.findByText("항목별 판정 없음 · 다음 스크래핑 때 재판정됩니다")).toBeInTheDocument();
    expect(screen.queryAllByRole("meter")).toHaveLength(0);
  });

  it("404면 안내와 목록 링크", async () => {
    stubApi(null);
    renderDetail();
    expect(await screen.findByText(/공고를 찾을 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "목록으로" })).toHaveAttribute("href", "/");
  });

  it("URL로 직접 진입했으면 목록으로는 /", async () => {
    stubApi(makeDetail({ id: 1 }));
    const { location } = renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: /목록으로/ }));
    expect(location().pathname).toBe("/");
  });

  it("히스토리가 있으면 목록으로는 뒤로가기", async () => {
    stubApi(makeDetail({ id: 1 }));
    const { location } = renderDetail({ entries: ["/hidden", "/postings/1"] });
    await userEvent.click(await screen.findByRole("button", { name: /목록으로/ }));
    expect(location().pathname).toBe("/hidden");
  });

  describe("북마크·숨김", () => {
    it("App 목록에 있으면 목록 상태를 보여준다", async () => {
      stubApi(makeDetail({ id: 1, bookmarked: false }));
      renderDetail({ postings: [makePosting({ id: 1, bookmarked: true })] });
      expect(await screen.findByRole("button", { name: "북마크 해제" })).toHaveClass("on");
    });

    it("목록에 없으면 상세 응답을 쓰고, 토글은 상세 응답 Posting으로 호출한 뒤 반영한다", async () => {
      const d = makeDetail({ id: 1, bookmarked: false });
      stubApi(d);
      const { onToggleBookmark } = renderDetail({ postings: [makePosting({ id: 2 })] });
      await userEvent.click(await screen.findByRole("button", { name: "북마크" }));
      expect(onToggleBookmark).toHaveBeenCalledWith(expect.objectContaining({ id: 1, bookmarked: false, description: d.description }));
      expect(await screen.findByRole("button", { name: "북마크 해제" })).toHaveClass("on");
    });

    it("목록에 없는 공고의 토글이 실패하면 그대로", async () => {
      stubApi(makeDetail({ id: 1, hidden: false }));
      const { onToggleHidden } = renderDetail();
      onToggleHidden.mockResolvedValue(false);
      await userEvent.click(await screen.findByRole("button", { name: "숨김" }));
      expect(onToggleHidden).toHaveBeenCalled();
      expect(screen.getByRole("button", { name: "숨김" })).not.toHaveClass("on");
    });
  });

  describe("피드백", () => {
    it("피드백이 없으면 버튼. 누르면 생성 중 비활성, 끝나면 목록", async () => {
      let release!: () => void;
      const fetch = stubApi(makeDetail({ id: 1, feedback: null }), () => new Promise((r) => (release = () => r(json({ posting_id: 1, feedback: feedback() })))));
      renderDetail();
      await userEvent.click(await screen.findByRole("button", { name: "피드백 생성" }));
      expect(fetch).toHaveBeenCalledWith("/api/postings/1/feedback", { method: "POST" });
      expect(button()).toBeDisabled();
      expect(button()).toHaveTextContent("생성 중…");
      expect(button()!.querySelector(".spinner")).not.toBeNull();

      release();
      expect(await screen.findByText("경력: Redis 매칭 큐 설계 강조")).toBeInTheDocument();
      expect(button()).toBeNull();
    });

    it("현재 이력서 기준 피드백이 있으면 목록만", async () => {
      stubApi(makeDetail({ id: 1, feedback: feedback() }));
      renderDetail();
      expect(await screen.findByText("성과: 지연 수치화")).toBeInTheDocument();
      expect(button()).toBeNull();
    });

    it("이전 이력서 기준이면 접어 두고 버튼을 보여준다", async () => {
      stubApi(makeDetail({ id: 1, feedback: feedback({ current: false }) }));
      renderDetail();
      const old = (await screen.findByText("이전 이력서 기준 피드백")).closest("details")!;
      expect(old).not.toHaveAttribute("open");
      expect(within(old).getByText("성과: 지연 수치화")).toBeInTheDocument();
      expect(button()).toHaveTextContent("피드백 생성");
    });

    it("401이면 버튼 자리에 로그인 안내, 로그인이 확인되면 버튼으로 돌아온다", async () => {
      stubApi(makeDetail({ id: 1 }), () => json({ code: "login_required", provider: "claude", message: "claude 로그인이 필요합니다", login_command: "claude login" }, 401));
      const { onRequireLogin, setLoginRequired } = renderDetail();
      await userEvent.click(await screen.findByRole("button", { name: "피드백 생성" }));
      await waitFor(() => expect(onRequireLogin).toHaveBeenCalledWith("claude 로그인이 필요합니다"));
      setLoginRequired(true);
      expect(screen.getByText("claude 로그인이 필요합니다")).toBeInTheDocument();
      expect(button()).toBeNull();

      setLoginRequired(false);
      expect(screen.queryByText("claude 로그인이 필요합니다")).not.toBeInTheDocument();
      expect(button()).toHaveTextContent("피드백 생성");
    });

    it("409면 스크래핑 중 toast", async () => {
      stubApi(makeDetail({ id: 1 }), () => json({ code: "job_running", message: "job running" }, 409));
      const { onToast } = renderDetail();
      await userEvent.click(await screen.findByRole("button", { name: "피드백 생성" }));
      await waitFor(() => expect(onToast).toHaveBeenCalledWith("스크래핑이 끝난 뒤 다시 시도해주세요", "error"));
      expect(button()).toBeEnabled();
    });

    it("502·400이면 서버 message toast", async () => {
      stubApi(makeDetail({ id: 1 }), () => json({ code: "llm_error", message: "LLM 호출 실패" }, 502));
      const { onToast } = renderDetail();
      await userEvent.click(await screen.findByRole("button", { name: "피드백 생성" }));
      await waitFor(() => expect(onToast).toHaveBeenCalledWith("LLM 호출 실패", "error"));
    });
  });
});
