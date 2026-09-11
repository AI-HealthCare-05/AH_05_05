# 369 light-clay 재작업 독립 검수

## 판정

2차 홈·챗 후보의 시각 요청 충족: PASS. 전체 57개 gallery 및 기능 회귀 검증 완료 판정과는 구분한다.

Appllama 스킬과 motion/performance/simulator-loop 지침을 직접 읽고 기존 React/Vite 모바일 웹에 맞춰 적용했다. Appllama MCP는 없어 출시 앱 실시간 조사 주장은 하지 않는다. 로컬 사용자 승인 home/chat 레퍼런스와 실제 before/after 캡처를 직접 비교했다. 사용자 명시 light-clay가 일반 미니멀 스타일보다 우선한다.

## 초기 결함과 보완

- 이전 1px 경계와 낮은 농도 외부 그림자는 표면 곡률이 약해 통통한 재질로 읽히지 않았다. 밝은 윗면, 상하 안쪽 명암, 짧은 확산 그림자와 일관된 곡률을 적용한 2차 후보는 탭·primary·secondary·챗 말풍선에서 같은 가벼운 클레이 재질로 읽힌다.
- 1차 홈의 복약 메모와 큰 카드가 평면적으로 남았다. 2차에서 secondary 재질과 큰 카드 가장자리 명암을 연결해 개선했다. 전체 깊이는 과도하게 무겁지 않다.
- 1차 챗에서 내부 근거 버튼과 부모 말풍선 하단 그림자가 중첩됐다. 2차에서 내부 깊이를 줄여 구분을 유지했다.
- 1차 loading/disabled 버튼의 불투명 primary gradient가 비활성 표면을 덮는 회귀를 브라우저에서 재현했다. 2차는 enabled 조건과 disabled 중립 표면으로 보완됐고, 실제 챗 PNG에서 중립 상태 복원을 확인했다.

## 직접 확인한 증거

`design-plans/369-clay-revision/screenshots/`의 before/after-home-medication-selected-390x844.png 및 before/after-chat-history-390x844.png를 직접 판독했다. first-pass 미완료 이미지는 최종 근거로 사용하지 않았다.

2차에서 기존 내용·배치·로고 누락이나 명백한 텍스트 겹침은 발견하지 않았다. navy/teal 본문과 primary의 흰 문구는 읽히며, 기존 요청인 mint-white/teal/navy와 가볍고 통통한 표면을 충족한다. 추가 장식은 요구하지 않는다.

## 대비 보정 확인

초기 gradient stop 계산에서 primary는 `4.32:1`, danger는 `3.46:1`로 기존 색보다 대비가 약해진 점을 발견했다. 최종 소스는 primary 상단을 primary 95% + white 5%, danger 상단을 danger-strong 92% + white 8%로 보정했으며, 곡면 inset과 전체 부피 구조는 유지했다.

Lead가 최종 브라우저 computed style로 실행한 테스트는 첫 sRGB stop과 실제 흰 문구의 대비를 primary `4.734:1`, danger `5.000:1`로 보고했다. 테스트 코드와 최종 stop은 독립 확인했지만 이 실행을 검수자가 중복 실행하지는 않았다. 수치는 첫 stop 기준이므로 gradient의 모든 픽셀과 모든 상태를 포괄하는 인증으로 확대 해석하지 않는다.

별도 브라우저 판독에서는 14px 흰 문구, loading/disabled 전환 250ms 뒤 중립 표면 `#F2F4F5`와 문구 `#879290`, 다음 버튼의 2px teal focus outline을 확인했다.

## 검증 한계

이 판정은 위 두 화면의 정적 시각 검수다. 57개 gallery 전체, 키보드 focus 실제 이동, 오류·대기·hover·press 전체 사이클, 확대 텍스트 최종 재검증은 별도 기능/회귀 검증 결과와 합쳐야 한다. 정적 PNG로 모션·실기기 safe-area·60fps 또는 정식 dark theme PASS를 주장하지 않는다. 최종 테스트를 검수자가 중복 실행하거나 57개 전체를 독립 재검수하지 않았다. 검수자는 제품 파일을 수정하지 않았다.
