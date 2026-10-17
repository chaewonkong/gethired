# spec - PDF 지원하기
## 목표
- pdf 이력서, 경력기술서도 추가 가능하다

## 기능
- 사용자가 이력서로 *.md 외에 .pdf를 추가할 수 있다.
- 추가된 pdf를 읽어 필요한 데이터를 추출할 수 있다.

## 검증 방법
resume/resume.md와 resume/resume.pdf는 동일 파일이므로 이 두 파일로 정합성 테스트를 수행한다.
- 별도 sandbox 내에 이 repository를 clone하고, pdf를 추가하는 테스트를 수행. pdf 추가시 내용을 정상적으로 읽을 수 있다.
- resume.md, resume.pdf를 번갈아 추가해보며 정합성이 일치하는지를 검증한다.
- 업로드 화면에서 md, pdf 모두 지원함을 알 수 있다.

## 결정 사항 (2026-10-17)
- PDF는 백엔드에서 텍스트를 추출해 기존 프로필 프롬프트에 넣는다 (`pypdf`). LLM에 PDF를 직접 넘기지 않는다 (provider 간 일관성)
- 업로드는 `PUT /api/resume/{name}`에 파일 바이트를 그대로 보낸다. 기존 JSON `{content}` 형식은 폐기
- 파일 크기 제한 없음. 서버는 스트리밍으로 디스크에 쓴다 (디자이너 포트폴리오 등 수백 MB 허용)
- 대신 LLM 입력은 문서당 50,000자 상한. 넘으면 뒤를 잘라 `[이하 생략]`을 붙인다. md에도 같은 규칙
- 텍스트를 추출할 수 없는 PDF(스캔·이미지)는 업로드 시점에 400으로 거부하고 toast로 알린다. OCR은 범위 밖
- 추출 결과 확인은 `just resume-text [파일...]` 디버그 스크립트(`backend/out/resume_text/`)
- 정합성 판정: md 프로필과 pdf 프로필의 구조 필드(`core_skills`, `domains`, `years_experience`, `preferences`)가 일치하면 통과. `summary` 등 서술 필드는 비교하지 않는다
- 커밋되는 테스트 픽스처는 합성 PDF. 실제 resume.md/resume.pdf 비교는 로컬 라이브 검증으로만
- 실행 계획: `design/plans/plan-0009.md`
