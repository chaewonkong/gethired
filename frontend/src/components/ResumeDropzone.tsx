import { DragEvent, useRef, useState } from "react";

/** 업로드할 수 없는 파일이 있으면 사유, 없으면 null */
export function invalidResumeFiles(files: File[]): string | null {
  const bad = files.filter((f) => !f.name.endsWith(".md") && !f.name.endsWith(".pdf"));
  if (bad.length) return `md 또는 pdf 파일만 업로드할 수 있습니다: ${bad.map((f) => f.name).join(", ")}`;
  return null;
}

export function ResumeDropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const files = [...e.dataTransfer.files];
    if (files.length) onFiles(files);
  };

  return (
    <div
      className={`dropzone${over ? " over" : ""}`}
      role="button"
      tabIndex={0}
      aria-label="이력서 파일 업로드"
      onClick={() => input.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          input.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 16V4m0 0-5 5m5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <strong>이력서 파일을 끌어다 놓거나 클릭해서 선택하세요</strong>
      <span className="meta">Markdown(.md) · PDF(.pdf) · 여러 파일 가능</span>
      <input
        ref={input}
        type="file"
        accept=".md,.pdf"
        multiple
        hidden
        data-testid="resume-input"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          const files = [...(e.target.files ?? [])];
          e.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </div>
  );
}
