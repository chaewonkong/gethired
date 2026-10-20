import { Company, Posting } from "../api";
import { useListPosition } from "../sessionState";
import { PostingCard } from "./PostingCard";

interface Props {
  postings: Posting[];
  byId: Record<string, Company>;
  onToggleBookmark: (p: Posting) => void;
  onToggleHidden: (p: Posting) => void;
}

export function HiddenTab({ postings, byId, onToggleBookmark, onToggleHidden }: Props) {
  const items = postings.filter((p) => p.hidden).sort((a, b) => b.score - a.score);
  useListPosition("/hidden", items.length > 0);

  return (
    <section className="panel">
      <div className="list">
        {items.length ? (
          items.map((p) => (
            <PostingCard key={p.id} posting={p} companyName={byId[p.company]?.display_name ?? p.company} onToggleBookmark={onToggleBookmark} onToggleHidden={onToggleHidden} />
          ))
        ) : (
          <div className="empty">
            숨긴 공고가 없습니다.
            <br />
            공고 카드의 눈 아이콘을 눌러 숨길 수 있습니다.
          </div>
        )}
      </div>
    </section>
  );
}
