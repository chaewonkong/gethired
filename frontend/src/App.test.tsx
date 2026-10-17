import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { Posting } from "./api";
import { makeCompany, makePosting, stubIntersectionObserver } from "./test/fixtures";

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function stubApi(postings: Posting[], routes: Record<string, Handler> = {}) {
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (routes[key]) return routes[key](init);
    if (key === "GET /api/postings") return json(postings);
    if (key === "GET /api/companies") return json([makeCompany()]);
    if (key === "GET /api/resume") return json([{ name: "resume.md", size: 10, updated_at: "2026-10-15T00:00:00+00:00" }]);
    if (key === "GET /api/settings/provider") return json({ provider: "claude", chosen: true });
    if (key === "GET /api/auth/status") return json({ provider: "claude", logged_in: true, login_command: "claude login" });
    if (key.endsWith("/bookmark") || key.endsWith("/hide")) return json({});
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const tab = (name: RegExp) => screen.getByRole("tab", { name });
const titles = () => screen.queryAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("App", () => {
  beforeEach(() => {
    stubIntersectionObserver();
  });

  it("공고를 불러오고 북마크 개수를 탭에 표시", async () => {
    stubApi([makePosting({ title: "a", bookmarked: true }), makePosting({ title: "b" })]);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "a" })).toBeInTheDocument();
    expect(within(tab(/북마크/)).getByText("1")).toBeInTheDocument();
  });

  it("별을 누르면 PUT 후 북마크 탭에 나타난다", async () => {
    const fetch = stubApi([makePosting({ id: 1, title: "a" })]);
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    expect(fetch).toHaveBeenCalledWith("/api/postings/1/bookmark", { method: "PUT" });
    expect(screen.getByRole("button", { name: "북마크 해제" })).toHaveClass("on");

    await userEvent.click(tab(/북마크/));
    expect(titles()).toEqual(["a"]);
  });

  it("북마크 탭에서 해제하면 DELETE 후 즉시 목록에서 빠진다", async () => {
    const fetch = stubApi([makePosting({ id: 1, title: "a", bookmarked: true }), makePosting({ id: 2, title: "b", bookmarked: true, score: 10 })]);
    render(<App />);
    await screen.findByRole("heading", { name: "a" });
    await userEvent.click(tab(/북마크/));
    expect(titles()).toEqual(["a", "b"]);

    await userEvent.click(screen.getAllByRole("button", { name: "북마크 해제" })[0]);
    expect(fetch).toHaveBeenCalledWith("/api/postings/1/bookmark", { method: "DELETE" });
    expect(titles()).toEqual(["b"]);
  });

  it("북마크 요청이 실패하면 별을 되돌리고 에러를 띄운다", async () => {
    stubApi([makePosting({ id: 1, title: "a" })], {
      "PUT /api/postings/1/bookmark": () => new Response("", { status: 500 }),
    });
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "북마크" })).not.toHaveClass("on"));
    expect(screen.getByText(/bookmark: 500/)).toBeInTheDocument();
  });

  it("숨김 버튼을 누르면 PUT 후 공고 탭에서 사라지고 숨김 탭에 나타난다", async () => {
    const fetch = stubApi([makePosting({ id: 1, title: "a" }), makePosting({ id: 2, title: "b", score: 10 })]);
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getAllByRole("button", { name: "숨김" })[0]);
    expect(fetch).toHaveBeenCalledWith("/api/postings/1/hide", { method: "PUT" });
    expect(titles()).toEqual(["b"]);
    expect(within(tab(/숨김/)).getByText("1")).toBeInTheDocument();

    await userEvent.click(tab(/숨김/));
    expect(titles()).toEqual(["a"]);
  });

  it("숨김 탭에서 해제하면 DELETE 후 숨김 탭에서 빠지고 공고 탭으로 돌아온다", async () => {
    const fetch = stubApi([makePosting({ id: 1, title: "a", hidden: true }), makePosting({ id: 2, title: "b", score: 10 })]);
    render(<App />);
    await screen.findByRole("heading", { name: "b" });
    expect(titles()).toEqual(["b"]);

    await userEvent.click(tab(/숨김/));
    await userEvent.click(screen.getByRole("button", { name: "숨김 해제" }));
    expect(fetch).toHaveBeenCalledWith("/api/postings/1/hide", { method: "DELETE" });
    expect(titles()).toEqual([]);

    await userEvent.click(tab(/공고/));
    expect(titles()).toEqual(["a", "b"]);
  });

  it("숨긴 공고는 북마크 탭과 북마크 개수에서 빠진다", async () => {
    stubApi([makePosting({ title: "a", bookmarked: true, hidden: true }), makePosting({ title: "b", bookmarked: true })]);
    render(<App />);
    await screen.findByRole("heading", { name: "b" });
    expect(within(tab(/북마크/)).getByText("1")).toBeInTheDocument();

    await userEvent.click(tab(/북마크/));
    expect(titles()).toEqual(["b"]);
  });

  it("숨김 요청이 실패하면 되돌리고 에러를 띄운다", async () => {
    stubApi([makePosting({ id: 1, title: "a" })], {
      "PUT /api/postings/1/hide": () => new Response("", { status: 500 }),
    });
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getByRole("button", { name: "숨김" }));
    await waitFor(() => expect(titles()).toEqual(["a"]));
    expect(screen.getByText(/hide: 500/)).toBeInTheDocument();
  });

  it("요청이 끝나기 전 같은 버튼을 다시 누르면 무시하고, 끝난 뒤에는 최신 상태로 토글한다", async () => {
    let release!: () => void;
    const fetch = stubApi([makePosting({ id: 1, title: "a" })], {
      "PUT /api/postings/1/bookmark": () => new Promise((r) => (release = () => r(new Response("{}")))),
    });
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    await userEvent.click(screen.getByRole("button", { name: "북마크 해제" }));
    const calls = () => fetch.mock.calls.filter(([path]) => String(path).endsWith("/bookmark"));
    expect(calls()).toEqual([["/api/postings/1/bookmark", { method: "PUT" }]]);
    expect(screen.getByRole("button", { name: "북마크 해제" })).toHaveClass("on");

    release();
    await userEvent.click(await screen.findByRole("button", { name: "북마크 해제" }));
    await waitFor(() => expect(calls()).toHaveLength(2));
    expect(calls()[1]).toEqual(["/api/postings/1/bookmark", { method: "DELETE" }]);
    expect(screen.getByRole("button", { name: "북마크" })).not.toHaveClass("on");
  });

  it("요청 중인 북마크와 숨김은 서로 막지 않는다", async () => {
    const fetch = stubApi([makePosting({ id: 1, title: "a" })], {
      "PUT /api/postings/1/bookmark": () => new Promise(() => {}),
    });
    render(<App />);
    await screen.findByRole("heading", { name: "a" });

    await userEvent.click(screen.getByRole("button", { name: "북마크" }));
    await userEvent.click(screen.getByRole("button", { name: "숨김" }));
    expect(fetch).toHaveBeenCalledWith("/api/postings/1/hide", { method: "PUT" });
  });

  it("스크래핑 시 로그인이 필요하면 안내 배너", async () => {
    stubApi([], { "POST /api/scrape": () => new Response("", { status: 401 }) });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "스크래핑 하기" }));
    expect(await screen.findByText("Claude 로그인이 필요합니다.")).toBeInTheDocument();
  });

  it("회사 필터는 탭을 옮겼다 돌아와도 유지된다", async () => {
    stubApi([makePosting({ title: "a", company: "toss" }), makePosting({ title: "b", company: "naver", score: 10 })], {
      "GET /api/companies": () => new Response(JSON.stringify([makeCompany(), makeCompany({ company: "naver", display_name: "네이버" })])),
    });
    render(<App />);
    await screen.findByRole("heading", { name: "a" });
    await userEvent.click(screen.getByRole("button", { name: /^회사 필터/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /토스/ }));
    expect(titles()).toEqual(["b"]);

    await userEvent.click(tab(/북마크/));
    await userEvent.click(tab(/공고/));
    expect(titles()).toEqual(["b"]);
  });

  it("회사 탭으로 전환", async () => {
    stubApi([]);
    render(<App />);
    await userEvent.click(await screen.findByRole("tab", { name: /회사/ }));
    expect(await screen.findByRole("table")).toHaveTextContent("토스");
  });

  describe("관심회사", () => {
    const companies = () => [makeCompany(), makeCompany({ company: "naver", display_name: "네이버", interested: false })];
    const companiesRoute = { "GET /api/companies": () => new Response(JSON.stringify(companies())) };

    it("관심회사가 아닌 회사의 공고는 모든 탭과 배지, 필터 옵션에서 빠진다", async () => {
      stubApi([
        makePosting({ title: "a", company: "toss", bookmarked: true }),
        makePosting({ title: "n", company: "naver", bookmarked: true }),
        makePosting({ title: "nh", company: "naver", hidden: true }),
      ], companiesRoute);
      render(<App />);
      await screen.findByRole("heading", { name: "a" });
      expect(titles()).toEqual(["a"]);
      expect(within(tab(/북마크/)).getByText("1")).toBeInTheDocument();
      expect(within(tab(/숨김/)).queryByText(/\d/)).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /^회사 필터/ }));
      expect(screen.queryByRole("checkbox", { name: /네이버/ })).not.toBeInTheDocument();
      expect(screen.getByRole("checkbox", { name: /토스/ })).toBeInTheDocument();

      await userEvent.click(tab(/북마크/));
      expect(titles()).toEqual(["a"]);
      await userEvent.click(tab(/숨김/));
      expect(titles()).toEqual([]);
    });

    it("회사 탭에서 별을 켜면 PUT 후 해당 회사 공고가 나타난다", async () => {
      const fetch = stubApi([makePosting({ title: "a", company: "toss" }), makePosting({ title: "n", company: "naver", score: 10 })], {
        ...companiesRoute,
        "PUT /api/companies/naver/interest": () => new Response("{}"),
      });
      render(<App />);
      await screen.findByRole("heading", { name: "a" });
      await userEvent.click(tab(/회사/));
      await userEvent.click(screen.getByRole("button", { name: "네이버 관심회사 추가" }));
      expect(fetch).toHaveBeenCalledWith("/api/companies/naver/interest", { method: "PUT" });
      expect(screen.getByRole("button", { name: "네이버 관심회사 해제" })).toHaveClass("on");

      await userEvent.click(tab(/공고/));
      expect(titles()).toEqual(["a", "n"]);
    });

    it("별 요청이 실패하면 되돌리고 에러를 띄운다", async () => {
      stubApi([], { ...companiesRoute, "PUT /api/companies/naver/interest": () => new Response("", { status: 500 }) });
      render(<App />);
      await userEvent.click(await screen.findByRole("tab", { name: /회사/ }));
      await userEvent.click(screen.getByRole("button", { name: "네이버 관심회사 추가" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "네이버 관심회사 추가" })).not.toHaveClass("on"));
      expect(screen.getByText(/interest: 500/)).toBeInTheDocument();
    });

    it("마지막 관심회사를 해제하면 DELETE 후 회사 선택 화면", async () => {
      const fetch = stubApi([], { ...companiesRoute, "DELETE /api/companies/toss/interest": () => new Response("{}") });
      render(<App />);
      await userEvent.click(await screen.findByRole("tab", { name: /회사/ }));
      await userEvent.click(screen.getByRole("button", { name: "토스 관심회사 해제" }));
      expect(fetch).toHaveBeenCalledWith("/api/companies/toss/interest", { method: "DELETE" });
      expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
    });
  });
});
