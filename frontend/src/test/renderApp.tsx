import { render } from "@testing-library/react";
import { ReactElement } from "react";
import { Location, MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import App from "../App";

interface Options {
  /** 히스토리 항목. 마지막이 현재 위치 */
  entries?: string[];
  /** 주면 ui를 이 경로 패턴의 Route로 렌더한다 (useParams용) */
  route?: string;
}

/** MemoryRouter로 감싸 렌더한다. location()은 현재 위치, rerender도 같은 Router 안에서 */
export function renderInRouter(ui: ReactElement, { entries = ["/"], route }: Options = {}) {
  const current: { location: Location | null } = { location: null };
  function Probe() {
    current.location = useLocation();
    return null;
  }
  const routed = (el: ReactElement) =>
    route ? (
      <Routes>
        <Route path={route} element={el} />
        <Route path="*" element={null} />
      </Routes>
    ) : (
      el
    );
  const wrap = (el: ReactElement) => (
    <MemoryRouter initialEntries={entries} initialIndex={entries.length - 1}>
      {routed(el)}
      <Probe />
    </MemoryRouter>
  );
  const utils = render(wrap(ui));
  return { ...utils, rerender: (el: ReactElement) => utils.rerender(wrap(el)), location: () => current.location! };
}

export const renderApp = (path = "/") => renderInRouter(<App />, { entries: [path] });
