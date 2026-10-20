import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { test, expect, Page } from "@playwright/test";
import { resetState, uploadResume } from "./helpers";

// README 데모 GIF 녹화용 골든 패스. 데모 모드 백엔드(E2E_DEMO=1) 위에서만 돈다.
test.describe.configure({ retries: 0 });

const PAUSE = 900;
const DEMO_COMPANIES = ["토스", "당근", "카카오", "네이버"];
const videoOut = process.env.DEMO_VIDEO_OUT ?? path.join(process.env.E2E_TMP!, "demo.webm");

test.beforeAll(() => {
  if (process.env.E2E_DEMO !== "1") throw new Error("E2E_DEMO=1 로 실행해야 한다 (데모 모드 백엔드)");
});

test.beforeEach(() => resetState());

// 비디오 파일은 page가 닫힌 뒤 완성된다. 실패해도 복사해 디버깅에 쓴다
test.afterEach(async ({ page }) => {
  const video = page.video();
  await page.close();
  if (!video) return;
  mkdirSync(path.dirname(videoOut), { recursive: true });
  copyFileSync(await video.path(), videoOut);
});

const pause = (page: Page) => page.waitForTimeout(PAUSE);

test("골든 패스: 업로드 → AI 선택 → 관심회사 → 스크래핑 → 결과", async ({ page }) => {
  await page.goto("/");
  await pause(page);

  await uploadResume(page);
  const toast = page.getByRole("status").filter({ hasText: "이력서를 업로드했습니다" });
  await expect(toast).toBeVisible();
  await expect(toast).toHaveCount(0, { timeout: 5_000 });

  await expect(page.getByRole("heading", { name: "AI 선택" })).toBeVisible();
  await pause(page);
  const claude = page.getByRole("radiogroup").getByRole("radio", { name: "Claude Code" });
  await claude.click();
  await expect(claude.getByText("로그인됨")).toBeVisible();
  await pause(page);
  await page.getByRole("button", { name: "계속" }).click();

  await expect(page.getByRole("heading", { name: "관심회사 선택" })).toBeVisible();
  await pause(page);
  for (const name of DEMO_COMPANIES) {
    await page.getByRole("checkbox", { name }).check();
    await page.waitForTimeout(300);
  }
  await pause(page);
  await page.getByRole("button", { name: /^확인/ }).click();
  await expect(page.getByRole("tablist")).toBeVisible();
  await pause(page);

  await page.getByRole("button", { name: "스크래핑 하기" }).click();
  await expect(page.locator(".progress").filter({ hasText: "스크래핑 중…" })).toBeVisible();
  await expect(page.locator("article")).toHaveCount(8, { timeout: 20_000 });
  await page.waitForTimeout(2_000);

  const first = page.locator("article").first();
  const title = (await first.getByRole("heading", { level: 3 }).textContent())!;
  await first.click();
  await expect(page.getByRole("heading", { level: 2, name: title })).toBeVisible();
  await pause(page);
  await page.getByRole("button", { name: "피드백 생성" }).click();
  await expect(page.locator(".feedback li")).toHaveCount(3, { timeout: 10_000 });
  await page.locator(".feedback").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1_500);

  await page.getByRole("button", { name: /목록으로/ }).click();
  await expect(page.locator("article")).toHaveCount(8);
  await page.waitForTimeout(1_000);
});
