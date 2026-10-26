import { Company, Posting } from "../api";
import { useListPosition } from "../sessionState";
import { PostingCard } from "./PostingCard";

interface Props {
  /** App이 지원일 내림차순으로 정렬해 넘긴다 */
  postings: Posting[];
  byId: Record<string, Company>;
  onToggleBookmark: (p: Posting) => void;
  onToggleHidden: (p: Posting) => void;
  onToggleApplied: (p: Posting) => void;
}

export function AppliedTab({ postings, byId, onToggleBookmark, onToggleHidden, onToggleApplied }: Props) {
  useListPosition("/applied", postings.length > 0);

  return (
    <section className="panel">
      <div className="list">
        {postings.length ? (
          postings.map((p) => (
            <PostingCard key={p.id} posting={p} companyName={byId[p.company]?.display_name ?? p.company}
                         onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} onToggleApplied={onToggleApplied} />
          ))
        ) : (
          <div className="empty">
            지원한 공고가 없습니다.
            <br />
            공고 카드의 체크를 눌러 지원완료로 표시하세요.
          </div>
        )}
      </div>
    </section>
  );
}
