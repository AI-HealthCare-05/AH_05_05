# #456 Task B — 약봉투 선택 미리보기 확대

## 기준과 범위

- BASE: `6d5e852f044771e077e7080d28faca9f995600b1`
- 작업 worktree: `C:/dev/AH_05_05/.codex-work/456-preview-20260913`
- 공유 `ImageViewer`의 현재 production callsite는 `DocumentUploadPage` 한 곳뿐이다.
- OCR 2/5의 로컬 `OcrEnvelopeImageViewer`에서 사용 중인 fitted baseline, `100/150/200/300%` 확대 단계, 양방향 pan, touch target 표현을 OCR 코드 변경 없이 재사용했다.
- 이미지 클릭으로 닫지 않고 닫기 버튼 또는 Escape를 사용하며, 닫은 뒤 선택 사진 trigger로 focus가 복원된다.
- OCR 요청, 업로드, object URL 생성·해제, 처리 이미지 전환 로직은 변경하지 않았다.

## 변경 경로

- `frontend/src/shared/ui/ImageViewer.tsx`
- `frontend/tests/e2e/medication-registration-flow.spec.ts`
- `preview-report.md`

## RED

명령:

```text
wsl.exe env VITE_USE_MOCK=false PLAYWRIGHT_TEST_PORT=45547 /home/sdh080200/.nvm/versions/node/v22.23.1/bin/node node_modules/playwright/cli.js test tests/e2e/medication-registration-flow.spec.ts --config playwright.447.config.ts --workers=1 --retries=0 -g "선택한 약봉투 원본"
```

- exit `1`
- `2 failed`
- 320px와 390px 모두 `확대 비율` status가 없어 `100%` assertion에서 실패했다. Production 코드는 이 실행 뒤에 변경했다.

## GREEN

명령:

```text
wsl.exe env VITE_USE_MOCK=false PLAYWRIGHT_TEST_PORT=45547 /home/sdh080200/.nvm/versions/node/v22.23.1/bin/node node_modules/playwright/cli.js test tests/e2e/medication-registration-flow.spec.ts --config playwright.447.config.ts --workers=1 --retries=0 -g "선택한 약봉투 원본"
```

- exit `0`
- `2 passed (29.0s)`
- 320px와 390px에서 선택한 blob URL 유지, fitted 100% baseline, 150/200/300% 단계, min/max disabled 상태, 300% 양방향 pan, 44px 이상 controls, viewport overflow 방지, 이미지 클릭 시 viewer 유지, 닫기/Escape와 focus 복원, reopen 100%·scroll reset을 검증했다.

## 보존 스크린샷

- `artifacts/456-preview-20260913/document-upload-preview-zoom-320.png`
- `artifacts/456-preview-20260913/document-upload-preview-zoom-390.png`

## 제한과 미실행

- 사용자 승인 범위에 따라 focused RED/GREEN만 실행했다. 전체 suite와 `tsc`는 실행하지 않았고 root가 최종 `tsc`를 소유한다.
- `OcrReviewPage`와 그 2/5 viewer는 변경하지 않았다.
- primary checkout 변경, dependency 설치, PR, push, merge는 수행하지 않았다.
- 최종 commit HEAD는 자기 참조를 피하기 위해 handoff 메시지에서 정확히 보고한다.
