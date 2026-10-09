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
    if (key.endsWith("/bookmark")) return json({});
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

  it("스크래핑 시 로그인이 필요하면 안내 배너", async () => {
    stubApi([], { "POST /api/scrape": () => new Response("", { status: 401 }) });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "스크래핑 하기" }));
    expect(await screen.findByText("Claude 로그인이 필요합니다.")).toBeInTheDocument();
  });

  it("회사 탭으로 전환", async () => {
    stubApi([]);
    render(<App />);
    await userEvent.click(tab(/회사/));
    expect(await screen.findByRole("table")).toHaveTextContent("토스");
  });
});
