import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthStatus, Company, Provider, ResumeFile } from "./api";
import { renderApp } from "./test/renderApp";
import { makeCompany, stubIntersectionObserver } from "./test/fixtures";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const file = (name: string, content = "# resume") => new File([content], name, { type: name.endsWith(".pdf") ? "application/pdf" : "text/markdown" });
type Handler = (init?: RequestInit) => Response | Promise<Response>;

interface BackendInit {
  files?: string[];
  interested?: string[];
  provider?: Provider;
  chosen?: boolean;
  loggedIn?: Partial<Record<Provider, boolean>>;
}

/** resume/관심회사/provider/로그인 상태를 들고 있는 가짜 백엔드. routes로 경로별 응답을 덮어쓸 수 있다 */
function stubBackend(init: BackendInit = {}, routes: Record<string, Handler> = {}) {
  const files = new Map((init.files ?? []).map((n) => [n, "x"]));
  let interested = new Set(init.interested ?? []);
  let provider: Provider = init.provider ?? "claude";
  let chosen = init.chosen ?? true;
  const loggedIn: Record<Provider, boolean> = { claude: false, codex: false, ...init.loggedIn };
  const authBody = (): AuthStatus => ({ provider, logged_in: loggedIn[provider], login_command: `${provider} login` });
  const base: Company[] = [makeCompany({ company: "toss", display_name: "토스" }), makeCompany({ company: "naver", display_name: "네이버" })];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${path}`;
    if (routes[key]) return routes[key](init);
    if (key === "GET /api/settings/provider") return json({ provider, chosen });
    if (key === "GET /api/auth/status") return json(authBody());
    if (key === "PUT /api/settings/provider") {
      const p = JSON.parse(String(init!.body)).provider;
      if (p !== "claude" && p !== "codex") return json({ detail: `unknown provider: ${p}` }, 400);
      provider = p;
      chosen = true;
      return json(authBody());
    }
    if (method === "GET" && path === "/api/postings") return json([]);
    if (method === "GET" && path === "/api/companies") return json(base.map((c) => ({ ...c, interested: interested.has(c.company) })));
    if (method === "GET" && path === "/api/resume")
      return json([...files.keys()].sort().map((name): ResumeFile => ({ name, size: 1, updated_at: "2026-10-15T00:00:00+00:00" })));
    const resume = path.match(/^\/api\/resume\/(.+)$/);
    if (resume && method === "PUT") {
      files.set(decodeURIComponent(resume[1]), await (init!.body as Blob).text());
      return json({});
    }
    if (method === "PUT" && path === "/api/interests") {
      interested = new Set(JSON.parse(String(init!.body)).companies);
      return json({});
    }
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fetch);
  const calls = (key: string) => fetch.mock.calls.filter(([path, init]) => `${init?.method ?? "GET"} ${path}` === key).length;
  return {
    fetch,
    files,
    interested: () => interested,
    setting: () => ({ provider, chosen }),
    setLoggedIn: (p: Provider, v: boolean) => (loggedIn[p] = v),
    authCalls: () => calls("GET /api/auth/status"),
    putCalls: () => calls("PUT /api/settings/provider"),
  };
}

const drop = (files: File[]) => fireEvent.drop(screen.getByRole("button", { name: "이력서 파일 업로드" }), { dataTransfer: { files } });

describe("onboarding", () => {
  beforeEach(() => {
    stubIntersectionObserver();
  });

  it("resume가 없으면 업로드 화면, 업로드 후 toast가 2초 뒤 닫히면 회사 선택 화면", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend = stubBackend();
    renderApp();
    expect(await screen.findByRole("heading", { name: "이력서 업로드" })).toBeInTheDocument();

    drop([file("resume.md"), file("portfolio.md")]);
    expect(await screen.findByRole("status")).toHaveTextContent("이력서를 업로드했습니다");
    expect(backend.files.get("resume.md")).toBe("# resume");
    expect(backend.files.has("portfolio.md")).toBe(true);
    expect(screen.getByRole("heading", { name: "이력서 업로드" })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("toast를 직접 닫으면 바로 다음 단계로", async () => {
    stubBackend();
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md")]);
    await userEvent.click(await screen.findByRole("button", { name: "닫기" }));
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
  });

  it("md·pdf가 아닌 파일이 섞여 있으면 업로드하지 않고 알린다", async () => {
    const backend = stubBackend();
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md"), file("resume.txt"), file("photo.PDF")]);
    expect(await screen.findByRole("alert")).toHaveTextContent("md 또는 pdf 파일만 업로드할 수 있습니다: resume.txt, photo.PDF");
    expect(backend.files.size).toBe(0);
    expect(screen.getByRole("heading", { name: "이력서 업로드" })).toBeInTheDocument();
  });

  it("pdf는 바이트 그대로 올라가고 목록에 나타난다", async () => {
    const backend = stubBackend();
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.pdf", "%PDF-1.4 fake")]);
    expect(await screen.findByRole("status")).toHaveTextContent("이력서를 업로드했습니다");
    expect(backend.files.get("resume.pdf")).toBe("%PDF-1.4 fake");
    expect(backend.fetch).toHaveBeenCalledWith("/api/resume/resume.pdf", expect.objectContaining({ method: "PUT", headers: { "Content-Type": "application/octet-stream" } }));
    await userEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
  });

  it("1MB를 넘는 파일도 업로드한다", async () => {
    const backend = stubBackend();
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("big.md", "x".repeat(1024 * 1024 + 1))]);
    expect(await screen.findByRole("status")).toHaveTextContent("이력서를 업로드했습니다");
    expect(backend.files.get("big.md")).toHaveLength(1024 * 1024 + 1);
  });

  it("서버가 400으로 거부한 파일은 detail을 toast로 보여주고 나머지는 올린다", async () => {
    const detail = "텍스트를 추출할 수 없는 PDF입니다 (스캔·이미지 PDF): scan.pdf";
    const backend = stubBackend({}, { "PUT /api/resume/scan.pdf": () => json({ detail }, 400) });
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("scan.pdf"), file("resume.md")]);
    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(backend.files.has("scan.pdf")).toBe(false);
    expect(backend.files.get("resume.md")).toBe("# resume");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
  });

  it("업로드가 400 외로 실패하면 에러 배너", async () => {
    const backend = stubBackend({}, { "PUT /api/resume/resume.md": () => new Response("", { status: 500 }) });
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md"), file("portfolio.md")]);
    expect(await screen.findByText("Error: resume: 500")).toBeInTheDocument();
    expect(backend.files.size).toBe(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("클릭으로 파일 선택해 업로드할 수 있다", async () => {
    const backend = stubBackend();
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    await userEvent.upload(screen.getByTestId("resume-input"), file("resume.md"));
    await waitFor(() => expect(backend.files.has("resume.md")).toBe(true));
  });

  it("resume는 있고 관심회사가 없으면 회사 선택부터. 0개 확인은 거부, 선택 후 확인하면 저장하고 공고 화면", async () => {
    const backend = stubBackend({ files: ["resume.md"] });
    renderApp();
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox").every((c) => !(c as HTMLInputElement).checked)).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: /^확인/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("관심회사를 1개 이상 선택하세요");
    expect(backend.fetch).not.toHaveBeenCalledWith("/api/interests", expect.anything());

    await userEvent.click(screen.getByRole("checkbox", { name: /네이버/ }));
    await userEvent.click(screen.getByRole("button", { name: /^확인/ }));
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
    expect([...backend.interested()]).toEqual(["naver"]);
  });

  it("resume가 비어 있고 관심회사가 있으면 업로드 후 회사 선택 없이 공고 화면", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubBackend({ interested: ["toss"] });
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md")]);
    await screen.findByRole("status");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "관심회사 선택" })).not.toBeInTheDocument();
  });

  it("둘 다 있으면 바로 공고 화면", async () => {
    stubBackend({ files: ["resume.md"], interested: ["toss"] });
    renderApp();
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
  });
});

describe("provider step", () => {
  const radio = (name: string) => screen.getByRole("radio", { name });
  const advance = (ms: number) =>
    act(() => {
      vi.advanceTimersByTime(ms);
    });

  beforeEach(() => {
    stubIntersectionObserver();
  });

  it("업로드 → AI 선택 → 관심회사 → 공고 화면. 카드 선택이 저장하고 계속은 다시 저장하지 않는다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend = stubBackend({ chosen: false });
    renderApp();
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md")]);
    await screen.findByRole("status");
    advance(2000);

    expect(await screen.findByRole("heading", { name: "AI 선택" })).toBeInTheDocument();
    expect(radio("Claude Code")).toHaveAttribute("aria-checked", "true");
    await userEvent.click(radio("Codex"));
    await waitFor(() => expect(backend.setting()).toEqual({ provider: "codex", chosen: true }));
    expect(radio("Codex")).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByText("codex login")).toBeInTheDocument();
    expect(radio("Codex")).toHaveTextContent("로그인 필요");
    expect(screen.getByRole("heading", { name: "AI 선택" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "계속" }));
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
    expect(backend.putCalls()).toBe(1);

    await userEvent.click(screen.getByRole("checkbox", { name: /네이버/ }));
    await userEvent.click(screen.getByRole("button", { name: /^확인/ }));
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
  });

  it("chosen이면 AI 선택을 건너뛴다", async () => {
    stubBackend({ files: ["resume.md"], chosen: true });
    renderApp();
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "AI 선택" })).not.toBeInTheDocument();
  });

  it("resume·관심회사가 있고 provider만 없으면 AI 선택부터. 미로그인이라도 계속하면 현재 선택을 저장하고 공고 화면", async () => {
    const backend = stubBackend({ files: ["resume.md"], interested: ["toss"], chosen: false });
    renderApp();
    expect(await screen.findByRole("heading", { name: "AI 선택" })).toBeInTheDocument();
    expect(radio("Claude Code")).toHaveAttribute("aria-checked", "true");
    expect(await screen.findByText("claude login")).toBeInTheDocument();
    expect(radio("Claude Code")).toHaveTextContent("로그인 필요");

    await userEvent.click(screen.getByRole("button", { name: "계속" }));
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
    expect(backend.setting()).toEqual({ provider: "claude", chosen: true });
    expect(backend.putCalls()).toBe(1);
  });

  it("provider가 codex로 미리 정해져 있으면 Codex가 선택돼 있다", async () => {
    stubBackend({ files: ["resume.md"], provider: "codex", chosen: false });
    renderApp();
    await screen.findByRole("heading", { name: "AI 선택" });
    expect(radio("Codex")).toHaveAttribute("aria-checked", "true");
    expect(radio("Claude Code")).toHaveAttribute("aria-checked", "false");
  });

  it("auth 응답을 기다리지 않고 첫 화면을 그린다. 배지는 확인 중", async () => {
    stubBackend({ files: ["resume.md"], chosen: false }, { "GET /api/auth/status": () => new Promise(() => {}) });
    renderApp();
    expect(await screen.findByRole("heading", { name: "AI 선택" })).toBeInTheDocument();
    expect(radio("Claude Code")).toHaveTextContent("확인 중");
  });

  it("저장이 실패하면 선택을 되돌리고 에러를 띄운다", async () => {
    const backend = stubBackend({ files: ["resume.md"], chosen: false }, { "PUT /api/settings/provider": () => new Response("", { status: 500 }) });
    renderApp();
    await screen.findByRole("heading", { name: "AI 선택" });
    await userEvent.click(radio("Codex"));
    await waitFor(() => expect(radio("Claude Code")).toHaveAttribute("aria-checked", "true"));
    expect(screen.getByText(/provider: 500/)).toBeInTheDocument();
    expect(backend.setting().chosen).toBe(false);
    expect(screen.getByRole("heading", { name: "AI 선택" })).toBeInTheDocument();
  });

  describe("폴링", () => {
    it("응답 후 3초 뒤 다시 조회한다", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const backend = stubBackend({ files: ["resume.md"], chosen: false });
      renderApp();
      await screen.findByText("claude login");
      expect(backend.authCalls()).toBe(1);
      advance(2000);
      expect(backend.authCalls()).toBe(1);
      advance(1000);
      expect(backend.authCalls()).toBe(2);
    });

    it("응답이 오기 전에는 겹쳐 호출하지 않는다", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const pendingAuth: ((r: Response) => void)[] = [];
      const backend = stubBackend({ files: ["resume.md"], chosen: false }, {
        "GET /api/auth/status": () => new Promise<Response>((r) => pendingAuth.push(r)),
      });
      renderApp();
      await screen.findByRole("heading", { name: "AI 선택" });
      await waitFor(() => expect(backend.authCalls()).toBe(1)); // 폴링 effect는 렌더 뒤 비동기로 시작
      advance(10000);
      expect(backend.authCalls()).toBe(1);

      pendingAuth[0](json({ provider: "claude", logged_in: false, login_command: "claude login" }));
      await screen.findByText("claude login");
      advance(3000);
      expect(backend.authCalls()).toBe(2);
    });

    it("로그인되면 배지가 바뀌고 폴링이 멈춘다", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const backend = stubBackend({ files: ["resume.md"], chosen: false });
      renderApp();
      await screen.findByText("claude login");
      backend.setLoggedIn("claude", true);
      advance(3000);
      await waitFor(() => expect(radio("Claude Code")).toHaveTextContent("로그인됨"));
      const n = backend.authCalls();
      advance(10000);
      expect(backend.authCalls()).toBe(n);
    });

    it("provider를 바꾸면 새 provider 상태로 배지가 바뀐다", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const backend = stubBackend({ files: ["resume.md"], chosen: false, loggedIn: { claude: true } });
      renderApp();
      await waitFor(() => expect(radio("Claude Code")).toHaveTextContent("로그인됨"));
      const n = backend.authCalls();
      advance(10000);
      expect(backend.authCalls()).toBe(n);

      await userEvent.click(radio("Codex"));
      await screen.findByText("codex login");
      backend.setLoggedIn("codex", true);
      advance(3000);
      await waitFor(() => expect(radio("Codex")).toHaveTextContent("로그인됨"));
    });
  });
});

describe("resume manager", () => {
  beforeEach(() => {
    stubIntersectionObserver();
  });

  function stubWithDelete(names: string[]) {
    const backend = stubBackend({ files: names, interested: ["toss"] });
    const inner = backend.fetch.getMockImplementation()!;
    backend.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
      const m = path.match(/^\/api\/resume\/(.+)$/);
      if (m && init?.method === "DELETE") {
        backend.files.delete(decodeURIComponent(m[1]));
        return json({});
      }
      return inner(path, init);
    });
    return backend;
  }

  const openManager = async () => {
    await userEvent.click(await screen.findByRole("button", { name: "이력서" }));
    return screen.getByRole("dialog");
  };

  it("파일 목록을 보여주고, 업로드하면 toast만 띄우고 화면 유지", async () => {
    const backend = stubWithDelete(["resume.md"]);
    renderApp();
    const dialog = await openManager();
    expect(dialog).toHaveTextContent("resume.md");

    drop([file("resume.md", "new"), file("portfolio.pdf")]);
    expect(await screen.findByRole("status")).toHaveTextContent("이력서를 업로드했습니다");
    expect(backend.files.get("resume.md")).toBe("new");
    expect(await screen.findByText("portfolio.pdf")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
  });

  it("파일을 삭제하면 목록에서 빠지고, 마지막 파일을 삭제하면 업로드 화면", async () => {
    const backend = stubWithDelete(["a.md", "b.md"]);
    renderApp();
    await openManager();

    await userEvent.click(screen.getByRole("button", { name: "a.md 삭제" }));
    expect(backend.fetch).toHaveBeenCalledWith("/api/resume/a.md", { method: "DELETE" });
    await waitFor(() => expect(screen.queryByText("a.md")).not.toBeInTheDocument());
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "b.md 삭제" }));
    expect(await screen.findByRole("heading", { name: "이력서 업로드" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Esc나 닫기 버튼으로 닫힌다", async () => {
    stubWithDelete(["a.md"]);
    renderApp();
    await openManager();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "이력서 창 닫기" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
