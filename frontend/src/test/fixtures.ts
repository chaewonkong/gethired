import { vi } from "vitest";
import { Company, Posting, PostingDetail } from "../api";

let seq = 0;

export function makePosting(over: Partial<Posting> = {}): Posting {
  const id = over.id ?? ++seq;
  return {
    id,
    company: "toss",
    external_id: String(id),
    title: `Backend Engineer ${id}`,
    summary: "summary",
    tech_stack: ["Go"],
    fit_level: "good",
    score: 70,
    gaps: [],
    fit_reason: "reason",
    apply_url: `https://example.com/${id}`,
    deadline: null,
    category: "Backend",
    scraped_at: "2026-10-09T00:00:00+00:00",
    first_seen_at: "2026-10-09T00:00:00+00:00",
    bookmarked: false,
    hidden: false,
    breakdown: null,
    ...over,
  };
}

export function makeDetail(over: Partial<PostingDetail> = {}): PostingDetail {
  return {
    ...makePosting(over),
    description: "본문",
    requirements: [{ text: "Go 3년 이상", fit: "met" }],
    preferred: [{ text: "Kubernetes 운영 경험", fit: "partial" }],
    breakdown: { skills: 30, domain: 20, seniority: 15, preferred: 5 },
    feedback: null,
    ...over,
  };
}

export function makeCompany(over: Partial<Company> = {}): Company {
  return {
    company: "toss",
    display_name: "토스",
    careers_url: "https://toss.im/career",
    last_run: null,
    interested: true,
    ...over,
  };
}

/** IntersectionObserver 대체: 테스트에서 intersect()로 sentinel 노출을 흉내낸다 */
export function stubIntersectionObserver() {
  const observers: { cb: IntersectionObserverCallback; els: Element[] }[] = [];
  class FakeIO {
    private entry: { cb: IntersectionObserverCallback; els: Element[] };
    constructor(cb: IntersectionObserverCallback) {
      this.entry = { cb, els: [] };
      observers.push(this.entry);
    }
    observe(el: Element) {
      this.entry.els.push(el);
    }
    disconnect() {
      observers.splice(observers.indexOf(this.entry), 1);
    }
  }
  vi.stubGlobal("IntersectionObserver", FakeIO);
  return {
    intersect() {
      for (const o of [...observers]) {
        o.cb(o.els.map((target) => ({ target, isIntersecting: true }) as IntersectionObserverEntry), {} as IntersectionObserver);
      }
    },
  };
}
