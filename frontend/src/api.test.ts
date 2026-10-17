import { describe, expect, it, vi } from "vitest";
import { api, JobRunningError, LoginRequiredError } from "./api";

function stubFetch(status = 200, body: unknown = {}) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("api", () => {
  it("GET 응답을 JSON으로", async () => {
    stubFetch(200, [{ company: "toss" }]);
    expect(await api.companies()).toEqual([{ company: "toss" }]);
  });

  it("GET 실패는 경로와 상태코드가 담긴 에러", async () => {
    stubFetch(500);
    await expect(api.postings()).rejects.toThrow("/api/postings: 500");
  });

  it("setBookmark: on이면 PUT, off면 DELETE", async () => {
    const fetch = stubFetch();
    await api.setBookmark(7, true);
    await api.setBookmark(7, false);
    expect(fetch.mock.calls).toEqual([
      ["/api/postings/7/bookmark", { method: "PUT" }],
      ["/api/postings/7/bookmark", { method: "DELETE" }],
    ]);
  });

  it("setBookmark 실패는 에러", async () => {
    stubFetch(404);
    await expect(api.setBookmark(1, true)).rejects.toThrow("bookmark: 404");
  });

  it("setHidden: on이면 PUT, off면 DELETE", async () => {
    const fetch = stubFetch();
    await api.setHidden(7, true);
    await api.setHidden(7, false);
    expect(fetch.mock.calls).toEqual([
      ["/api/postings/7/hide", { method: "PUT" }],
      ["/api/postings/7/hide", { method: "DELETE" }],
    ]);
  });

  it("setHidden 실패는 에러", async () => {
    stubFetch(404);
    await expect(api.setHidden(1, true)).rejects.toThrow("hide: 404");
  });

  it("startScrape 401이면 LoginRequiredError. body의 provider·message를 담는다", async () => {
    stubFetch(401, { code: "login_required", provider: "codex", message: "codex 로그인이 필요합니다" });
    const err = await api.startScrape().catch((e) => e);
    expect(err).toBeInstanceOf(LoginRequiredError);
    expect(err.provider).toBe("codex");
    expect(err.message).toBe("codex 로그인이 필요합니다");
  });

  it("startScrape 401 body가 없어도 LoginRequiredError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    const err = await api.startScrape().catch((e) => e);
    expect(err).toBeInstanceOf(LoginRequiredError);
    expect(err.provider).toBeNull();
  });

  it("providerSetting·authStatus는 GET", async () => {
    const fetch = stubFetch(200, { provider: "codex", chosen: false });
    expect(await api.providerSetting()).toEqual({ provider: "codex", chosen: false });
    expect(fetch).toHaveBeenCalledWith("/api/settings/provider");
    await api.authStatus();
    expect(fetch).toHaveBeenCalledWith("/api/auth/status");
  });

  it("setProvider는 PUT 후 auth 상태를 돌려준다", async () => {
    const body = { provider: "codex", logged_in: false, login_command: "codex login" };
    const fetch = stubFetch(200, body);
    expect(await api.setProvider("codex")).toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/settings/provider", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "codex" }),
    });
  });

  it("setProvider 409면 JobRunningError에 message", async () => {
    stubFetch(409, { code: "job_running", message: "스크래핑 중입니다" });
    const err = await api.setProvider("codex").catch((e) => e);
    expect(err).toBeInstanceOf(JobRunningError);
    expect(err.message).toBe("스크래핑 중입니다");
  });

  it("setProvider 400은 일반 Error", async () => {
    stubFetch(400, { detail: "unknown provider: x" });
    const err = await api.setProvider("x" as never).catch((e) => e);
    expect(err).not.toBeInstanceOf(JobRunningError);
    expect(err).not.toBeInstanceOf(LoginRequiredError);
    expect(err.message).toBe("provider: 400");
  });

  it("startScrape 성공 시 job_id", async () => {
    const fetch = stubFetch(202, { job_id: "j1", status: "running" });
    expect(await api.startScrape()).toMatchObject({ job_id: "j1" });
    expect(fetch).toHaveBeenCalledWith("/api/scrape", { method: "POST" });
  });
});
