import { test, expect, Page } from "@playwright/test";
import { pickFirstCompany, resetState, setAuth, uploadResume } from "./helpers";

// 로그인 배지 폴링은 3초 주기
const POLL = { timeout: 10_000 };

type ProviderName = "Claude Code" | "Codex";

test.beforeEach(() => resetState());

async function chooseProvider(page: Page, name: ProviderName) {
  await expect(page.getByRole("heading", { name: "AI 선택" })).toBeVisible();
  await page.getByRole("radiogroup").getByRole("radio", { name }).click();
}

async function onboard(page: Page, provider: ProviderName) {
  await page.goto("/");
  await uploadResume(page);
  await chooseProvider(page, provider);
  await page.getByRole("button", { name: "계속" }).click();
  await pickFirstCompany(page);
}

test.fixme("온보딩: 업로드 → AI 선택(Codex) → 계속 → 관심회사 → 메인, 새로고침해도 유지", async ({ page }) => {
  await onboard(page, "Codex");
  await page.reload();
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI 선택" })).toHaveCount(0);
});

test.fixme("AI 선택: 미로그인 배지 → 로그인하면 새로고침 없이 로그인됨", async ({ page }) => {
  await page.goto("/");
  await uploadResume(page);
  await chooseProvider(page, "Codex");
  const codex = page.getByRole("radiogroup").getByRole("radio", { name: "Codex" });
  await expect(codex.getByText("로그인 필요")).toBeVisible(POLL);
  await expect(codex.locator("code")).toHaveText("codex login");

  setAuth({ codex: true });
  await expect(codex.getByText("로그인됨")).toBeVisible(POLL);
});

test.fixme("메인: 미로그인 provider로 스크래핑 → 배너에 로그인 명령 → 로그인하면 배너 사라짐", async ({ page }) => {
  await onboard(page, "Codex");
  await page.getByRole("button", { name: "스크래핑 하기" }).click();
  const banner = page.locator(".banner").filter({ has: page.getByRole("button", { name: "AI 변경" }) });
  await expect(banner).toBeVisible();
  await expect(banner.locator("code")).toHaveText("codex login");

  setAuth({ codex: true });
  await expect(banner).toHaveCount(0, POLL);
});
