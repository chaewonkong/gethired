import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { Company, ResumeFile } from "./api";
import { makeCompany, stubIntersectionObserver } from "./test/fixtures";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const file = (name: string, content = "# resume") => new File([content], name, { type: "text/markdown" });

/** resume/관심회사 상태를 들고 있는 가짜 백엔드 */
function stubBackend(init: { files?: string[]; interested?: string[] } = {}) {
  const files = new Map((init.files ?? []).map((n) => [n, "x"]));
  let interested = new Set(init.interested ?? []);
  const base: Company[] = [makeCompany({ company: "toss", display_name: "토스" }), makeCompany({ company: "naver", display_name: "네이버" })];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "GET" && path === "/api/postings") return json([]);
    if (method === "GET" && path === "/api/companies") return json(base.map((c) => ({ ...c, interested: interested.has(c.company) })));
    if (method === "GET" && path === "/api/resume")
      return json([...files.keys()].sort().map((name): ResumeFile => ({ name, size: 1, updated_at: "2026-10-15T00:00:00+00:00" })));
    const resume = path.match(/^\/api\/resume\/(.+)$/);
    if (resume && method === "PUT") {
      files.set(decodeURIComponent(resume[1]), JSON.parse(String(init!.body)).content);
      return json({});
    }
    if (method === "PUT" && path === "/api/interests") {
      interested = new Set(JSON.parse(String(init!.body)).companies);
      return json({});
    }
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fetch);
  return { fetch, files, interested: () => interested };
}

const drop = (files: File[]) => fireEvent.drop(screen.getByRole("button", { name: "이력서 파일 업로드" }), { dataTransfer: { files } });

describe("onboarding", () => {
  beforeEach(() => {
    stubIntersectionObserver();
  });

  it("resume가 없으면 업로드 화면, 업로드 후 toast가 2초 뒤 닫히면 회사 선택 화면", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend = stubBackend();
    render(<App />);
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
    render(<App />);
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md")]);
    await userEvent.click(await screen.findByRole("button", { name: "닫기" }));
    expect(await screen.findByRole("heading", { name: "관심회사 선택" })).toBeInTheDocument();
  });

  it("md가 아닌 파일이 섞여 있으면 업로드하지 않고 알린다", async () => {
    const backend = stubBackend();
    render(<App />);
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("resume.md"), file("resume.pdf")]);
    expect(await screen.findByRole("alert")).toHaveTextContent("md 파일만 업로드할 수 있습니다: resume.pdf");
    expect(backend.files.size).toBe(0);
    expect(screen.getByRole("heading", { name: "이력서 업로드" })).toBeInTheDocument();
  });

  it("1MB를 넘는 파일은 거부한다", async () => {
    const backend = stubBackend();
    render(<App />);
    await screen.findByRole("heading", { name: "이력서 업로드" });
    drop([file("big.md", "x".repeat(1024 * 1024 + 1))]);
    expect(await screen.findByRole("alert")).toHaveTextContent("1MB");
    expect(backend.files.size).toBe(0);
  });

  it("클릭으로 파일 선택해 업로드할 수 있다", async () => {
    const backend = stubBackend();
    render(<App />);
    await screen.findByRole("heading", { name: "이력서 업로드" });
    await userEvent.upload(screen.getByTestId("resume-input"), file("resume.md"));
    await waitFor(() => expect(backend.files.has("resume.md")).toBe(true));
  });

  it("resume는 있고 관심회사가 없으면 회사 선택부터. 0개 확인은 거부, 선택 후 확인하면 저장하고 공고 화면", async () => {
    const backend = stubBackend({ files: ["resume.md"] });
    render(<App />);
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
    render(<App />);
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
    render(<App />);
    expect(await screen.findByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
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
    render(<App />);
    const dialog = await openManager();
    expect(dialog).toHaveTextContent("resume.md");

    drop([file("resume.md", "new"), file("portfolio.md")]);
    expect(await screen.findByRole("status")).toHaveTextContent("이력서를 업로드했습니다");
    expect(backend.files.get("resume.md")).toBe("new");
    expect(await screen.findByText("portfolio.md")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "스크래핑 하기" })).toBeInTheDocument();
  });

  it("파일을 삭제하면 목록에서 빠지고, 마지막 파일을 삭제하면 업로드 화면", async () => {
    const backend = stubWithDelete(["a.md", "b.md"]);
    render(<App />);
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
    render(<App />);
    await openManager();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openManager();
    await userEvent.click(screen.getByRole("button", { name: "이력서 창 닫기" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
