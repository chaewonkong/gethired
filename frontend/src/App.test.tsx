import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { Job, Posting, Provider } from "./api";
import { makeCompany, makePosting, stubIntersectionObserver } from "./test/fixtures";

type Handler = (init?: RequestInit) => Response | Promise<Response>;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

interface ApiInit {
  provider?: Provider;
  loggedIn?: Partial<Record<Provider, boolean>>;
}

/** provider·로그인 상태를 들고 있는 가짜 API. 스크래핑은 미로그인이면 401, 아니면 running job */
function stubApi(postings: Posting[], routes: Record<string, Handler> = {}, opts: ApiInit = {}) {
  let provider: Provider = opts.provider ?? "claude";
  const loggedIn: Record<Provider, boolean> = { claude: true, codex: true, ...opts.loggedIn };
  const authBody = () => ({ provider, logged_in: loggedIn[provider], login_command: `${provider} login` });
  const job: Job = { job_id: "j1", status: "running", started_at: "2026-10-15T00:00:00+00:00", finished_at: null, cost_usd: 0, companies: {} };
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    if (routes[key]) return routes[key](init);
    if (key === "GET /api/postings") return json(postings);
    if (key === "GET /api/companies") return json([makeCompany()]);
    if (key === "GET /api/resume") return json([{ name: "resume.md", size: 10, updated_at: "2026-10-15T00:00:00+00:00" }]);
    if (key === "GET /api/settings/provider") return json({ provider, chosen: true });
    if (key === "GET /api/auth/status") return json(authBody());
    if (key === "PUT /api/settings/provider") {
      provider = JSON.parse(String(init!.body)).provider;
      return json(authBody());
    }
    if (key === "POST /api/scrape") {
      if (!loggedIn[provider]) return json({ code: "login_required", provider, message: `${provider} 로그인이 필요합니다` }, 401);
      return json({ job_id: "j1" }, 202);
    }
    if (key === "GET /api/scrape/j1") return json(job);
    if (key.endsWith("/bookmark") || key.endsWith("/hide")) return json({});
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fetch);
  const calls = (key: string) => fetch.mock.calls.filter(([path, init]) => `${init?.method ?? "GET"} ${path}` === key).length;
  return Object.assign(fetch, {
    provider: () => provider,
    setLoggedIn: (p: Provider, v: boolean) => (loggedIn[p] = v),
    putCalls: () => calls("PUT /api/settings/provider"),
    authCalls: () => calls("GET /api/auth/status"),
  });
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

  describe("provider", () => {
    const scrape = async () => userEvent.click(await screen.findByRole("button", { name: "스크래핑 하기" }));
    const banner = () => screen.getByText(/^(Claude Code|Codex) 로그인이 필요합니다\.$/).closest(".banner")!;
    const openAi = async () => {
      await userEvent.click(screen.getByRole("button", { name: "AI" }));
      return screen.getByRole("dialog", { name: "AI 선택" });
    };

    it("스크래핑 401이면 provider별 배너: 이름과 로그인 명령", async () => {
      stubApi([], {}, { provider: "codex", loggedIn: { codex: false } });
      render(<App />);
      await scrape();
      expect(await screen.findByText("Codex 로그인이 필요합니다.")).toBeInTheDocument();
      await waitFor(() => expect(banner().querySelector("code")).toHaveTextContent("codex login"));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("claude면 Claude Code 배너", async () => {
      stubApi([], {}, { loggedIn: { claude: false } });
      render(<App />);
      await scrape();
      expect(await screen.findByText("Claude Code 로그인이 필요합니다.")).toBeInTheDocument();
      await waitFor(() => expect(banner().querySelector("code")).toHaveTextContent("claude login"));
    });

    it("401 body가 없고 auth 응답 전이면 기본 문구", async () => {
      stubApi([], { "POST /api/scrape": () => new Response("", { status: 401 }), "GET /api/auth/status": () => new Promise(() => {}) });
      render(<App />);
      await scrape();
      expect(await screen.findByText("Claude Code 로그인이 필요합니다.")).toBeInTheDocument();
      expect(banner()).toHaveTextContent("로그인이 필요합니다. 터미널에서 로그인 후 다시 시도해주세요.");
    });

    it("스크래핑 409면 toast를 띄우고 job 폴링을 하지 않는다", async () => {
      const fetch = stubApi([], { "POST /api/scrape": () => json({ code: "job_running", message: "job running" }, 409) });
      render(<App />);
      await scrape();
      expect(await screen.findByText("다른 곳에서 스크래핑 중입니다")).toBeInTheDocument();
      expect(fetch.mock.calls.some(([path]) => String(path).startsWith("/api/scrape/"))).toBe(false);
      expect(document.querySelector(".banner.error")).toBeNull();
    });

    it("배너의 AI 변경으로 모달을 열고, 전환하면 배너 문구가 바뀐다", async () => {
      const fetch = stubApi([], {}, { provider: "codex", loggedIn: { claude: false, codex: false } });
      render(<App />);
      await scrape();
      await screen.findByText("Codex 로그인이 필요합니다.");
      await userEvent.click(screen.getByRole("button", { name: "AI 변경" }));
      const dialog = screen.getByRole("dialog", { name: "AI 선택" });
      expect(within(dialog).getByRole("radio", { name: "Codex" })).toHaveAttribute("aria-checked", "true");

      await userEvent.click(within(dialog).getByRole("radio", { name: "Claude Code" }));
      expect(await screen.findByText("Claude Code 로그인이 필요합니다.")).toBeInTheDocument();
      await waitFor(() => expect(banner().querySelector("code")).toHaveTextContent("claude login"));
      expect(fetch.provider()).toBe("claude");
      expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveTextContent("로그인 필요");
    });

    it("로그인되면 배너가 사라지고 폴링이 멈춘다", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const fetch = stubApi([], {}, { provider: "codex", loggedIn: { codex: false } });
      render(<App />);
      await scrape();
      await screen.findByText("Codex 로그인이 필요합니다.");
      await waitFor(() => expect(banner().querySelector("code")).toHaveTextContent("codex login"));

      fetch.setLoggedIn("codex", true);
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      await waitFor(() => expect(screen.queryByText("Codex 로그인이 필요합니다.")).not.toBeInTheDocument());
      const n = fetch.authCalls();
      act(() => {
        vi.advanceTimersByTime(10000);
      });
      expect(fetch.authCalls()).toBe(n);
    });

    it("헤더 AI 버튼 → 모달. 전환은 PUT, 닫았다 다시 열어도 유지. Esc·바깥 클릭으로 닫힌다", async () => {
      const fetch = stubApi([]);
      render(<App />);
      await screen.findByRole("button", { name: "스크래핑 하기" });
      let dialog = await openAi();
      expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveAttribute("aria-checked", "true");
      await waitFor(() => expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveTextContent("로그인됨"));

      await userEvent.click(within(dialog).getByRole("radio", { name: "Codex" }));
      await waitFor(() => expect(fetch.provider()).toBe("codex"));
      expect(fetch).toHaveBeenCalledWith("/api/settings/provider", expect.objectContaining({ method: "PUT", body: JSON.stringify({ provider: "codex" }) }));
      await waitFor(() => expect(within(dialog).getByRole("radio", { name: "Codex" })).toHaveTextContent("로그인됨"));

      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      dialog = await openAi();
      expect(within(dialog).getByRole("radio", { name: "Codex" })).toHaveAttribute("aria-checked", "true");

      await userEvent.click(dialog.parentElement!);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      await openAi();
      await userEvent.click(screen.getByRole("button", { name: "AI 선택 창 닫기" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("스크래핑 중에는 안내만 보이고 카드를 눌러도 바뀌지 않는다", async () => {
      const fetch = stubApi([]);
      render(<App />);
      await scrape();
      await waitFor(() => expect(screen.getByRole("button", { name: /스크래핑/ })).toBeDisabled());
      const dialog = await openAi();
      expect(within(dialog).getByText("스크래핑 중에는 바꿀 수 없습니다")).toBeInTheDocument();
      await userEvent.click(within(dialog).getByRole("radio", { name: "Codex" }));
      expect(fetch.putCalls()).toBe(0);
      expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveAttribute("aria-checked", "true");
    });

    it("PUT 409면 toast를 띄우고 선택을 되돌린다", async () => {
      const fetch = stubApi([], { "PUT /api/settings/provider": () => json({ code: "job_running", message: "스크래핑 중에는 바꿀 수 없습니다" }, 409) });
      render(<App />);
      await screen.findByRole("button", { name: "스크래핑 하기" });
      const dialog = await openAi();
      await userEvent.click(within(dialog).getByRole("radio", { name: "Codex" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("스크래핑 중에는 바꿀 수 없습니다");
      await waitFor(() => expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveAttribute("aria-checked", "true"));
      expect(fetch.provider()).toBe("claude");
    });

    it("PUT이 그 외로 실패하면 에러 배너와 함께 되돌린다", async () => {
      stubApi([], { "PUT /api/settings/provider": () => new Response("", { status: 500 }) });
      render(<App />);
      await screen.findByRole("button", { name: "스크래핑 하기" });
      const dialog = await openAi();
      await userEvent.click(within(dialog).getByRole("radio", { name: "Codex" }));
      await waitFor(() => expect(within(dialog).getByRole("radio", { name: "Claude Code" })).toHaveAttribute("aria-checked", "true"));
      expect(screen.getByText(/provider: 500/)).toBeInTheDocument();
    });

    it("메인 화면에서는 모달·배너가 없으면 auth를 조회하지 않는다", async () => {
      const fetch = stubApi([]);
      render(<App />);
      await screen.findByRole("button", { name: "스크래핑 하기" });
      expect(fetch.authCalls()).toBe(0);
      await openAi();
      await waitFor(() => expect(fetch.authCalls()).toBe(1));
    });
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
