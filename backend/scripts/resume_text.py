"""이력서 텍스트 추출 확인 (디버그용). RESUME_DIR의 파일을 extract_text로 뽑아 out/resume_text/<name>.txt에 저장."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import RESUME_DIR  # noqa: E402
from app.profile import source_files  # noqa: E402
from app.resume import TEXT_LIMIT, extract_text  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "out" / "resume_text"
TRUNCATED_MARK = "\n[이하 생략]"


def main() -> int:
    only = sys.argv[1:]
    files = [f for f in source_files() if not only or f.name in only]
    missing = set(only) - {f.name for f in files}
    for name in sorted(missing):
        print(f"{name}: not found in {RESUME_DIR}", file=sys.stderr)
    if not files:
        print(f"no *.md / *.pdf files in {RESUME_DIR}", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for f in files:
        try:
            text = extract_text(f)
        except ValueError as e:
            failed += 1
            print(f"{f.name:30} failed  {e}")
            continue
        (OUT / f"{f.name}.txt").write_text(text)
        truncated = text.endswith(TRUNCATED_MARK)
        note = f"truncated at {TEXT_LIMIT}" if truncated else ("EMPTY" if not text else "")
        print(f"{f.name:30} {len(text):>7} chars  {note}")
    print(f"\n{len(files) - failed}/{len(files)} written to {OUT}")
    return 1 if failed or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
