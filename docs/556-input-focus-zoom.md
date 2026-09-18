# #556 입력 포커스 자동 확대

2026-09-18 사용자 요청으로 #555 날짜 입력 박스 가로 넘침과 분리했다.

## 이관한 변경

- 최신 main `6768a8d`에서 분기한 `feature/556`.
- 메모 처방 select, 복용 일시 input의 실제 글자 크기 15→16px.
- 375·390·393·414·430px에서 위 컨트롤과 textarea의 렌더링 글자 크기를 검증하는 테스트.
- WebKit 기준: https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/ios/WKWebViewIOS.mm 의 `_zoomToFocusRect` 글자 크기 기반 확대 계산.

## 남은 범위

- 공통 Input과 각 페이지 input/select/textarea의 작은 글자 및 자동 포커스 조사·개선은 미완료.
- 실제 iOS 키보드 열기/닫기, 확대 상태의 페이지 이동 영향은 실기기 확인 대기.
- 16px 조건 검증을 실제 iPhone의 자동 확대 재현·해결 결과로 간주하지 않는다.
- 날짜 입력 박스 가로 넘침은 #555에 남기며 이 변경으로 해결했다고 표시하지 않는다.

## 검증 실행

```sh
node node_modules/playwright/cli.js test -c playwright.ios-input.config.ts
```

기존 공개 비교 서버의 main 원본/16px 후보는 이관 전과 동일한 빌드로 유지한다. 합성 데이터 전용이며 운영 데이터와 연결하지 않는다. PR·병합·운영 배포는 하지 않는다.
