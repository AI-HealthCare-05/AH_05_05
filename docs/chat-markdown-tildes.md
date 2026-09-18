# 챗봇 물결표 범위 표기 보존

## 요구사항과 원인

- 사용자가 챗봇 답변에서 여러 수치 범위 사이 문장에 취소선이 생기는 실제 화면을 제보했다.
- 관련 이슈: #571 (마크다운 특정 문자 이스케이프 적용).
- 최신 원격 main `6768a8d`에서 분기한 수정본을 `feature/571`로 옮겼다. #562/#563 등 다른 작업은 포함하지 않는다.
- ChatMarkdown은 remark-gfm의 기본 설정을 사용했다. 이 설정은 `~내용~`와 `~~내용~~`를 취소선으로 해석하므로 같은 문단의 `6~8`, `250~500` 같은 서로 다른 범위도 연결될 수 있다.
- 원문의 숫자나 의료 내용의 정확성을 검증하는 작업이 아니라, 전달받은 답변의 표시를 보존하는 프런트엔드 수정이다.

## 변경

- 챗봇 파서에서 `strikethrough` 구문만 비활성화한다. 물결표를 삭제하거나 정규식으로 전체 원문을 치환하지 않는다.
- CSS로 취소선만 가리거나 del 태그만 제거하면 구문 해석 시 소모된 물결표를 복구하지 못하므로 해당 방식은 사용하지 않는다.
- 표·제목·강조·목록·코드·HTTP(S) 링크와 기존 HTML/이미지 차단을 유지한다. 한 개뿐 아니라 두 개 물결표도 원문 그대로 보인다.
- 보고서 렌더러·백엔드·DB·저장된 답변은 변경하지 않는다. 기존 대화와 새 대화 모두 사용하는 ChatMarkdown에만 적용한다.

## 검증 (2026-09-18)

- 수정 전: 기존 안전한 Markdown 테스트 1건 통과, 물결표 보존 테스트 2건은 실제 del 요소 2개/3개로 실패했다.
- 수정 후: TypeScript 검사 통과. Chromium/WebKit 각 3건, 총 6건 통과.
- 검증 항목: 복수 범위, 두 개 물결표, 강조 내부 범위, 표 내부 범위, 인라인/펜스 코드, 이스케이프, 물결표 포함 URL, 기존 표/코드 스크롤과 안전한 링크·HTML 차단.
- 실제 앱에 브라우저 로컬 합성 대화 데이터를 공급한 검증이다. 운영 API·모델 답변 생성·실제 iPhone 기기·전체 CI 검증은 아니다.
- 전후 캡처와 실행 결과: `artifacts/chat-markdown-tildes/red/`, `artifacts/chat-markdown-tildes/green/`.

재현:

```bash
cd frontend
node node_modules/typescript/bin/tsc --noEmit
CHOKIDAR_USEPOLLING=true PLAYWRIGHT_TEST_PORT=44565 node node_modules/playwright/cli.js test -c playwright.chat-markdown.config.ts -g '물결표|저장된 AI 답변' --output=../artifacts/chat-markdown-tildes/green
```

근거: [remark-gfm 기본 singleTilde 설정](https://github.com/remarkjs/remark-gfm#options), [micromark 구문 비활성화 확장](https://github.com/micromark/micromark#syntaxextension). 설치된 라이브러리의 `strikethrough` 구문 이름도 대조했다.
