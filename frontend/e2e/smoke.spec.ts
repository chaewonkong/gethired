import { test, expect } from "@playwright/test";
import { readAuth, setAuth } from "./helpers";

test.beforeEach(() => setAuth({ claude: true, codex: false }));

test("첫 화면은 이력서 업로드", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "이력서 업로드" })).toBeVisible();
});

test("/api/auth/status는 가짜 claude CLI 결과를 반영한다", async ({ request }) => {
  expect(readAuth()).toEqual({ claude: true, codex: false });
  let res = await request.get("/api/auth/status");
  expect(res.ok()).toBe(true);
  expect(await res.json()).toMatchObject({ logged_in: true });

  setAuth({ claude: false });
  res = await request.get("/api/auth/status");
  expect(await res.json()).toMatchObject({ logged_in: false });
});
