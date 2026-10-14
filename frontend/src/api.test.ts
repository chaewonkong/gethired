import { describe, expect, it, vi } from "vitest";
import { api, LoginRequiredError } from "./api";

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

  it("startScrape 401이면 LoginRequiredError", async () => {
    stubFetch(401);
    await expect(api.startScrape()).rejects.toBeInstanceOf(LoginRequiredError);
  });

  it("startScrape 성공 시 job_id", async () => {
    const fetch = stubFetch(202, { job_id: "j1", status: "running" });
    expect(await api.startScrape()).toMatchObject({ job_id: "j1" });
    expect(fetch).toHaveBeenCalledWith("/api/scrape", { method: "POST" });
  });
});
