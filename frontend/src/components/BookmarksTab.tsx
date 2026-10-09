import { Company, Posting } from "../api";
import { PostingCard } from "./PostingCard";

interface Props {
  postings: Posting[];
  byId: Record<string, Company>;
  onToggleBookmark: (p: Posting) => void;
}

export function BookmarksTab({ postings, byId, onToggleBookmark }: Props) {
  const items = postings.filter((p) => p.bookmarked).sort((a, b) => b.score - a.score);

  return (
    <section className="panel">
      <div className="list">
        {items.length ? (
          items.map((p) => (
            <PostingCard key={p.id} posting={p} companyName={byId[p.company]?.display_name ?? p.company} onToggleBookmark={onToggleBookmark} />
          ))
        ) : (
          <div className="empty">
            북마크한 공고가 없습니다.
            <br />
            공고 카드의 ☆를 눌러 북마크하세요.
          </div>
        )}
      </div>
    </section>
  );
}
