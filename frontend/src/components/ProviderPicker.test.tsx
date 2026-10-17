import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthStatus } from "../api";
import { ProviderPicker } from "./ProviderPicker";

const auth = (over: Partial<AuthStatus> = {}): AuthStatus => ({ provider: "claude", logged_in: true, login_command: "claude login", ...over });
const radio = (name: string) => screen.getByRole("radio", { name });

describe("ProviderPicker", () => {
  it("radiogroup 안에 Claude Code·Codex 카드, 선택된 카드만 checked", () => {
    render(<ProviderPicker value="codex" auth={null} onSelect={() => {}} />);
    expect(screen.getByRole("radiogroup", { name: "AI 선택" })).toBeInTheDocument();
    expect(radio("Claude Code")).toHaveAttribute("aria-checked", "false");
    expect(radio("Codex")).toHaveAttribute("aria-checked", "true");
  });

  it("카드를 누르면 onSelect", async () => {
    const onSelect = vi.fn();
    render(<ProviderPicker value="claude" auth={auth()} onSelect={onSelect} />);
    await userEvent.click(radio("Codex"));
    expect(onSelect).toHaveBeenCalledWith("codex");
  });

  it("배지: auth 없으면 확인 중, 선택되지 않은 카드엔 배지 없음", () => {
    render(<ProviderPicker value="claude" auth={null} onSelect={() => {}} />);
    expect(radio("Claude Code")).toHaveTextContent("확인 중");
    expect(radio("Codex")).not.toHaveTextContent(/확인 중|로그인/);
  });

  it("배지: 다른 provider의 auth면 확인 중", () => {
    render(<ProviderPicker value="codex" auth={auth()} onSelect={() => {}} />);
    expect(radio("Codex")).toHaveTextContent("확인 중");
  });

  it("배지: 로그인됨", () => {
    render(<ProviderPicker value="claude" auth={auth()} onSelect={() => {}} />);
    expect(radio("Claude Code")).toHaveTextContent("로그인됨");
  });

  it("배지: 로그인 필요 + 로그인 명령은 code", () => {
    render(<ProviderPicker value="codex" auth={auth({ provider: "codex", logged_in: false, login_command: "codex login" })} onSelect={() => {}} />);
    const codex = radio("Codex");
    expect(codex).toHaveTextContent("로그인 필요 · 터미널에서 codex login");
    expect(codex.querySelector("code")).toHaveTextContent("codex login");
    expect(radio("Claude Code")).not.toHaveTextContent("로그인");
  });

  it("disabled면 클릭·키보드 선택 무시, 안내 문구", async () => {
    const onSelect = vi.fn();
    render(<ProviderPicker value="claude" auth={auth()} disabled onSelect={onSelect} />);
    expect(screen.getByText("스크래핑 중에는 바꿀 수 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("radiogroup")).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(radio("Codex"));
    radio("Codex").focus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("활성 상태에선 안내 문구가 없다", () => {
    render(<ProviderPicker value="claude" auth={auth()} onSelect={() => {}} />);
    expect(screen.queryByText("스크래핑 중에는 바꿀 수 없습니다")).not.toBeInTheDocument();
  });

  it("키보드: Tab은 선택된 카드로, 화살표로 이동, Enter·Space로 선택", async () => {
    const onSelect = vi.fn();
    render(<ProviderPicker value="claude" auth={auth()} onSelect={onSelect} />);
    await userEvent.tab();
    expect(radio("Claude Code")).toHaveFocus();

    await userEvent.keyboard("{ArrowRight}");
    expect(radio("Codex")).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith("codex");

    await userEvent.keyboard("{ArrowDown}");
    expect(radio("Claude Code")).toHaveFocus();
    await userEvent.keyboard(" ");
    expect(onSelect).toHaveBeenLastCalledWith("claude");

    await userEvent.keyboard("{ArrowLeft}");
    expect(radio("Codex")).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}");
    expect(radio("Claude Code")).toHaveFocus();
  });
});
