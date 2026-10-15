import { useEffect } from "react";
import { ResumeFile } from "../api";
import { formatTime } from "./PostingsTab";
import { ResumeDropzone } from "./ResumeDropzone";

interface Props {
  files: ResumeFile[];
  onUpload: (files: File[]) => void;
  onDelete: (name: string) => void;
  onClose: () => void;
}

const formatSize = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

export function ResumeModal({ files, onUpload, onDelete, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="resume-modal-title">
        <div className="modal-head">
          <h2 id="resume-modal-title">이력서</h2>
          <button type="button" className="modal-close" aria-label="이력서 창 닫기" onClick={onClose}>×</button>
        </div>
        <p className="meta">같은 이름의 파일을 올리면 교체됩니다. 모든 파일을 합쳐 프로필을 만들고, 다음 스크래핑부터 반영됩니다.</p>
        <ul className="resume-files">
          {files.map((f) => (
            <li key={f.name}>
              <span className="file-name">{f.name}</span>
              <span className="meta">{formatSize(f.size)} · {formatTime(f.updated_at)}</span>
              <button type="button" className="file-delete" aria-label={`${f.name} 삭제`} onClick={() => onDelete(f.name)}>삭제</button>
            </li>
          ))}
        </ul>
        <ResumeDropzone onFiles={onUpload} />
      </div>
    </div>
  );
}
