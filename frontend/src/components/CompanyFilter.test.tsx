import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeCompany } from "../test/fixtures";
import { CompanyFilter } from "./CompanyFilter";

const companies = [
  makeCompany(),
  makeCompany({ company: "naver", display_name: "네이버" }),
  makeCompany({ company: "kakao", display_name: "카카오" }),
];
const counts = { toss: 14, naver: 3, kakao: 0 };

function renderFilter(excluded: string[] = [], onChange = vi.fn()) {
  render(<CompanyFilter companies={companies} counts={counts} excluded={excluded} onChange={onChange} />);
  return { onChange, trigger: screen.getByRole("button", { name: /^회사 필터/ }) };
}

describe("CompanyFilter 라벨", () => {
  it("전체 선택이면 전체 회사", () => {
    expect(renderFilter([]).trigger).toHaveTextContent("전체 회사");
  });

  it("일부 선택이면 첫 회사 외 N곳", () => {
    expect(renderFilter(["kakao"]).trigger).toHaveTextContent("토스 외 1곳");
  });

  it("하나만 선택이면 그 회사 이름", () => {
    expect(renderFilter(["toss", "kakao"]).trigger).toHaveTextContent("네이버");
  });

  it("전부 해제면 선택 없음", () => {
    expect(renderFilter(["toss", "naver", "kakao"]).trigger).toHaveTextContent("선택 없음");
  });

  it("목록에 없는 회사가 해제 목록에 있어도 무시한다", () => {
    expect(renderFilter(["gone"]).trigger).toHaveTextContent("전체 회사");
  });
});

describe("CompanyFilter 드롭다운", () => {
  it("버튼을 누르면 열리고 바깥을 클릭하면 닫힌다", async () => {
    const { trigger } = renderFilter();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);

    await userEvent.click(document.body);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("트리거의 접근성 이름은 회사 필터 + 선택 요약", () => {
    expect(renderFilter(["kakao"]).trigger).toHaveAccessibleName("회사 필터: 토스 외 1곳");
  });

  it("Tab으로 포커스가 밖으로 나가면 닫힌다", async () => {
    render(
      <>
        <CompanyFilter companies={companies} counts={counts} excluded={[]} onChange={vi.fn()} />
        <button>after</button>
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: /^회사 필터/ }));
    await userEvent.tab();
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    for (let i = 0; i < 4; i++) await userEvent.tab();
    expect(screen.getByRole("button", { name: "after" })).toHaveFocus();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("Esc로 닫힌다", async () => {
    const { trigger } = renderFilter();
    await userEvent.click(trigger);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("드롭다운 안을 클릭해도 닫히지 않는다", async () => {
    const { trigger } = renderFilter();
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("checkbox", { name: /네이버/ }));
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("체크 상태는 해제 목록 반대, 회사별 건수 표시, 0건은 흐리게", async () => {
    const { trigger } = renderFilter(["naver"]);
    await userEvent.click(trigger);
    expect(screen.getByRole("checkbox", { name: /토스/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /네이버/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "토스 14" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "카카오 0" }).closest("label")).toHaveClass("zero");
    expect(screen.getByRole("checkbox", { name: /토스/ }).closest("label")).not.toHaveClass("zero");
  });

  it("체크를 끄면 해제 목록에 추가, 켜면 제거", async () => {
    const onChange = vi.fn();
    const { trigger } = renderFilter(["naver"], onChange);
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("checkbox", { name: /토스/ }));
    expect(onChange).toHaveBeenLastCalledWith(["naver", "toss"]);
    await userEvent.click(screen.getByRole("checkbox", { name: /네이버/ }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("전체 선택 상태면 전체 끄기 → 모든 회사 해제", async () => {
    const onChange = vi.fn();
    const { trigger } = renderFilter([], onChange);
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: "전체 끄기" }));
    expect(onChange).toHaveBeenCalledWith(["toss", "naver", "kakao"]);
  });

  it("일부라도 해제돼 있으면 전체 켜기 → 해제 목록 비움", async () => {
    const onChange = vi.fn();
    const { trigger } = renderFilter(["kakao"], onChange);
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: "전체 켜기" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
