import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { Page, expect } from "@playwright/test";

const tmp = process.env.E2E_TMP!;
export const authFile = path.join(tmp, "auth.json");
export const dbPath = path.join(tmp, "app.db");
export const resumeDir = path.join(tmp, "resume");

export type Auth = { claude: boolean; codex: boolean };
export const DEFAULT_AUTH: Auth = { claude: true, codex: false };

export function readAuth(): Auth {
  try {
    return { ...DEFAULT_AUTH, ...JSON.parse(readFileSync(authFile, "utf8")) };
  } catch {
    return { ...DEFAULT_AUTH };
  }
}

export function setAuth(patch: Partial<Auth>) {
  mkdirSync(tmp, { recursive: true });
  writeFileSync(authFile, JSON.stringify({ ...readAuth(), ...patch }) + "\n");
}

// 서버는 띄워둔 채 DB의 모든 행과 이력서 파일을 지운다. 백엔드가 DB_PATH·RESUME_DIR env를 따를 때만 효과가 있다.
export function resetState() {
  setAuth(DEFAULT_AUTH);
  if (existsSync(resumeDir)) for (const f of readdirSync(resumeDir)) rmSync(path.join(resumeDir, f));
  if (!existsSync(dbPath)) return;
  execFileSync("python3", ["-I", "-c", RESET_SQL, dbPath]);
}

const RESET_SQL = `
import sqlite3, sys
c = sqlite3.connect(sys.argv[1], timeout=10)
for (t,) in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
    c.execute(f'delete from "{t}"')
c.commit()
`;

export const resumeFile = {
  name: "resume.md",
  mimeType: "text/markdown",
  buffer: Buffer.from("# 홍길동\n\n백엔드 엔지니어 5년. Go, Redis, Kubernetes, PostgreSQL.\n"),
};

export async function uploadResume(page: Page) {
  await expect(page.getByRole("heading", { name: "이력서 업로드" })).toBeVisible();
  await page.getByTestId("resume-input").setInputFiles(resumeFile);
}

export async function pickFirstCompany(page: Page) {
  await expect(page.getByRole("heading", { name: "관심회사 선택" })).toBeVisible();
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: /^확인/ }).click();
  await expect(page.getByRole("tablist")).toBeVisible();
}
