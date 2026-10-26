import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, Breakdown, Company, Feedback, FitMark, JobRunningError, LlmError, LoginRequiredError, NotFoundError, Posting, PostingDetail as Detail, Requirement } from "../api";
import { ToastMessage } from "./Toast";
import { AppliedButton, Deadline, HideButton, StarButton } from "./PostingCard";

interface Props {
  /** App의 전체 공고. 북마크·숨김 상태는 여기 있으면 이걸 쓴다 (낙관적 업데이트 반영) */
  postings: Posting[];
  byId: Record<string, Company>;
  /** App 로그인 배너가 떠 있는지. 해제되면 로그인 안내를 버튼으로 되돌린다 */
  loginRequired: boolean;
  onToggleBookmark: (p: Posting) => Promise<boolean>;
  onToggleHidden: (p: Posting) => Promise<boolean>;
  onToggleApplied: (p: Posting) => Promise<boolean>;
  onRequireLogin: (message: string | null) => void;
  onToast: (text: string, kind: ToastMessage["kind"]) => void;
}

const AXES: { key: keyof Breakdown; label: string; max: number }[] = [
  { key: "skills", label: "핵심 기술", max: 35 },
  { key: "domain", label: "도메인·업무", max: 35 },
  { key: "seniority", label: "연차", max: 20 },
  { key: "preferred", label: "우대사항", max: 10 },
];

export function PostingDetail({ postings, byId, loginRequired, onToggleBookmark, onToggleHidden, onToggleApplied, onRequireLogin, onToast }: Props) {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const location = useLocation();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    api.posting(id).then(
      (d) => !cancelled && setDetail(d),
      (e) => !cancelled && setError(e),
    );
    return () => {
      cancelled = true;
    };
  }, [id]);

  const back = () => (location.key === "default" ? navigate("/") : navigate(-1));

  if (error instanceof NotFoundError || (!error && Number.isNaN(id))) {
    return (
      <section className="panel detail">
        <div className="empty">
          공고를 찾을 수 없습니다.
          <br />
          <Link to="/">목록으로</Link>
        </div>
      </section>
    );
  }
  if (error) return <section className="panel detail"><div className="banner error">{String(error)}</div></section>;
  if (!detail) return <section className="panel detail"><p className="meta">불러오는 중…</p></section>;

  // 목록에 없으면(목록 로드 전 직접 진입 등) 상세 응답을 쓰고, 토글 성공 시 그 값을 직접 바꾼다
  const listed = postings.find((p) => p.id === detail.id);
  const p: Posting = listed ?? detail;
  const toggle = (flag: "bookmarked" | "hidden", fn: (p: Posting) => Promise<boolean>) => async () => {
    if ((await fn(p)) && !listed) setDetail((d) => (d ? { ...d, [flag]: !p[flag] } : d));
  };
  const toggleApplied = async () => {
    if ((await onToggleApplied(p)) && !listed) {
      setDetail((d) => (d ? { ...d, application: p.application ? null : { applied_at: new Date().toISOString(), stage: null } } : d));
    }
  };
  const closed = p.deleted_at !== null;

  return (
    <section className="panel detail">
      <button type="button" className="back" onClick={back}>← 목록으로</button>
      <div className="card-head">
        <div className="co-logo">{(byId[p.company]?.display_name ?? p.company)[0]}</div>
        <div className="co-info">
          <div className="company">{byId[p.company]?.display_name ?? p.company}</div>
          <Deadline deadline={p.deadline} closed={closed} />
        </div>
        <span className={`level ${p.fit_level}`}>
          {p.fit_level} · {p.score}
        </span>
        <StarButton on={p.bookmarked} disabled={closed} onClick={toggle("bookmarked", onToggleBookmark)} />
        <HideButton on={p.hidden} disabled={closed} onClick={toggle("hidden", onToggleHidden)} />
        <AppliedButton on={p.application !== null} disabled={closed && p.application === null} onClick={toggleApplied} />
      </div>
      <h2>{detail.title}</h2>
      <a className="apply" href={detail.apply_url} target="_blank" rel="noopener noreferrer">
        지원하기 →
      </a>

      <section>
        <h3>공고</h3>
        <p className="summary">{detail.summary}</p>
        {detail.tech_stack.length > 0 && (
          <div className="chips">
            {detail.tech_stack.map((s) => (
              <span key={s} className="chip">{s}</span>
            ))}
          </div>
        )}
        {detail.description !== null && (
          <details className="body">
            <summary>공고 본문</summary>
            <div className="body-text">{detail.description}</div>
          </details>
        )}
      </section>

      <section>
        <h3>정합성</h3>
        <FitTable title="자격요건" items={detail.requirements} />
        <FitTable title="우대사항" items={detail.preferred} />
        <BreakdownBars breakdown={detail.breakdown} />
        <p className="reason">
          <strong>추천 이유</strong>
          {detail.fit_reason}
        </p>
        {detail.gaps.length > 0 && (
          <ul className="gaps">
            {detail.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        )}
      </section>

      <FeedbackSection
        postingId={detail.id}
        feedback={detail.feedback}
        loginRequired={loginRequired}
        onDone={(feedback) => setDetail((d) => (d ? { ...d, feedback } : d))}
        onRequireLogin={onRequireLogin}
        onToast={onToast}
      />
    </section>
  );
}

const FIT: Record<FitMark, { mark: string; label: string }> = {
  met: { mark: "✓", label: "충족" },
  partial: { mark: "△", label: "부분 충족" },
  unmet: { mark: "✗", label: "미충족" },
};

/** 요건별 충족 표: ✓ 초록 · △ 주황 · ✗ 빨강. fit null(판정 전 저장 행)은 회색 – */
export function FitTable({ title, items }: { title: string; items: Requirement[] | null }) {
  if (!items?.length) return null;
  return (
    <table className="fit-table" aria-label={title}>
      <caption>{title}</caption>
      <tbody>
        {items.map((r) => {
          const f = r.fit ? FIT[r.fit] : { mark: "–", label: "판정 없음" };
          return (
            <tr key={r.text}>
              <td className={`fit-mark ${r.fit ?? "none"}`} aria-label={f.label} title={f.label}>{f.mark}</td>
              <td>{r.text}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function BreakdownBars({ breakdown }: { breakdown: Breakdown | null }) {
  if (!breakdown) return <p className="meta">항목별 판정 없음 · 다음 스크래핑 때 재판정됩니다</p>;
  return (
    <div className="bars">
      {AXES.map(({ key, label, max }) => (
        <div key={key} className="bar-row">
          <span className="bar-label">{label}</span>
          <span className="bar-value">{breakdown[key]}/{max}</span>
          <div className="bar" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={breakdown[key]}>
            <div style={{ width: `${(breakdown[key] / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

interface FeedbackProps {
  postingId: number;
  feedback: Feedback | null;
  loginRequired: boolean;
  onDone: (f: Feedback) => void;
  onRequireLogin: (message: string | null) => void;
  onToast: (text: string, kind: ToastMessage["kind"]) => void;
}

function FeedbackSection({ postingId, feedback, loginRequired, onDone, onRequireLogin, onToast }: FeedbackProps) {
  const [generating, setGenerating] = useState(false);
  const [loginNotice, setLoginNotice] = useState<string | null>(null);

  const generate = async () => {
    setGenerating(true);
    try {
      onDone((await api.generateFeedback(postingId)).feedback);
    } catch (e) {
      if (e instanceof LoginRequiredError) {
        setLoginNotice(e.message);
        onRequireLogin(e.message);
      } else if (e instanceof JobRunningError) onToast("스크래핑이 끝난 뒤 다시 시도해주세요", "error");
      else if (e instanceof LlmError) onToast(e.message, "error");
      else onToast(String(e), "error");
    } finally {
      setGenerating(false);
    }
  };

  // App 배너가 로그인을 확인해 사라지면 안내도 버튼으로 돌아간다
  const action =
    loginNotice !== null && loginRequired ? (
      <p className="banner">{loginNotice}</p>
    ) : (
      <button type="button" className="btn" onClick={generate} disabled={generating}>
        {generating && <span className="spinner" aria-hidden="true" />}
        {generating ? "생성 중…" : "피드백 생성"}
      </button>
    );

  return (
    <section className="feedback">
      <h3>이력서 피드백</h3>
      {feedback?.current ? (
        <Items items={feedback.items} />
      ) : (
        <>
          {feedback && (
            <details>
              <summary>이전 이력서 기준 피드백</summary>
              <Items items={feedback.items} />
            </details>
          )}
          {action}
        </>
      )}
    </section>
  );
}

const Items = ({ items }: { items: string[] }) => (
  <ul>
    {items.map((x) => (
      <li key={x}>{x}</li>
    ))}
  </ul>
);
