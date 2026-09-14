# 튜토리얼 이미지 생성 기록 (#475)

## 승인 및 제작

- 약봉투 촬영, 복용 알림, 성분 합계, 근거 기반 챗봇의 4단계 구성을 사용자 승인 후 제작했습니다.
- 제작 도구: 기본 내장 imagegen (CLI/API 대체 경로 미사용).
- 형식: 투명 RGBA PNG, 1254 × 1254. 생성 원본의 알파와 비율을 유지합니다.
- 이미지 안에는 제품명·복용량·가상 성분 수치·의료적 보증 문구를 넣지 않습니다.
- 기존 튜토리얼의 설명 문구와 완료·이동 동작은 유지합니다.
- 챗봇 이미지는 현재 병아리의 크림색 상단 껍질, 민트 하단 껍질, 노란 얼굴을 따릅니다. 초기 참조 이미지 기반 결과에 투명 배경 대신 체크무늬가 생겨 제외하고, 동일한 캐릭터 특징을 명시하여 새로 생성했습니다.

## 파일 및 최종 생성 프롬프트

아래 파일은 `frontend/public/images/tutorial/`에 저장되어 있습니다.

### prescription-scan.png

```text
Use case: stylized-concept. Asset type: a final raster illustration for one screen of the RxVita mobile onboarding tutorial, NOT a screenshot or UI mockup. Style: refined soft 3D clay-like objects, smooth matte surfaces, gentle diffuse lighting, very restrained highlights and soft contact shadows, pale mint, deep teal and warm cream palette. Friendly and calm, clean readable silhouettes at 260px display size. Square 1024x1024 composition; all objects fully visible in the central 78% with generous empty margin on all sides. Genuinely transparent background with alpha, no opaque backdrop or platform. No text, letters, numbers, logos, watermarks, human hands, sparkles, excessive props or glossy reflections. Render one single illustration, not a grid. Subject: a teal-edged smartphone showing a cream prescription medication paper pouch inside four simple camera focus corners. Beside the phone, a small cream schedule card with a few teal rectangular blocks and small circular time markers, linked from the camera scene by one subtle curved arrow. Clearly communicate photographing a prescription pouch creates a medication schedule. Use only these main objects. Pouch has abstract blank strokes only, not readable writing. No diagnostic or approval badges.
```

### dose-reminder.png

```text
Use case: stylized-concept. Asset type: a final raster illustration for one screen of the RxVita mobile onboarding tutorial, NOT a screenshot or UI mockup. Style: refined soft 3D clay-like objects, smooth matte surfaces, gentle diffuse lighting, very restrained highlights and soft contact shadows, pale mint, deep teal and warm cream palette. Friendly and calm, clean readable silhouettes at 260px display size. Square 1024x1024 composition; all objects fully visible in the central 78% with generous empty margin on all sides. Genuinely transparent background with alpha, no opaque backdrop or platform. No text, letters, numbers, logos, watermarks, human hands, sparkles, excessive props or glossy reflections. Render one single illustration, not a grid. Subject: a simple cream analog clock with teal hands and sparse hour tick marks (no numerals), beside a teal-edged smartphone with one raised cream notification card carrying a small teal bell symbol. A small mint medication tray below contains just one cream tablet and one small capsule. Clearly communicate a reminder at the scheduled medication time, not encouragement to take more. Balanced compact arrangement with equal prominence to clock and notification. No character.
```

### ingredient-totals.png

```text
Use case: stylized-concept. Asset type: a final raster illustration for one screen of the RxVita mobile onboarding tutorial, NOT a screenshot or UI mockup. Style: refined soft 3D clay-like objects, smooth matte surfaces, gentle diffuse lighting, very restrained highlights and soft contact shadows, pale mint, deep teal and warm cream palette. Friendly and calm, clean readable silhouettes at 260px display size. Square 1024x1024 composition; all objects fully visible in the central 78% with generous empty margin on all sides. Genuinely transparent background with alpha, no opaque backdrop or platform. No text, letters, numbers, logos, watermarks, human hands, sparkles, excessive props or glossy reflections. Render one single illustration, not a grid. Subject: exactly two compact supplement containers, one warm cream and one pale mint, with plain labels containing only simple geometric marks. Two subtle flowing connectors lead from the containers to a single raised cream card showing one horizontal stacked bar with two differently toned teal segments and a thin neutral reference marker at the far right. Clearly communicate adding the ingredients of two products and comparing their combined amount to a reference. The abstract chart must have no numbers, labels or writing, no checkmark, no safety shield, no thumbs up, no visual implication that more supplements are better.
```

### chat-sources.png

```text
Create a new transparent PNG asset. Use case: stylized-concept. A final RxVita onboarding raster illustration, single square composition. Scene: one adorable small yellow chick peeking from a cracked egg, next to a cream speech bubble and a cream source-document card joined with one teal curved link. The chick has tiny black round eyes and an orange triangular beak, no limbs visible. Upper eggshell forms an oversized cream oval helmet with a jagged broken lower edge. The lower eggshell is a rounded pale mint capsule-shaped bowl, cream jagged rim around its middle, one fine zigzag crack down the front. The chick's yellow face is visible in the opening between the top and bottom shell. Match an elegant soft 3D app mascot, not cartoon outlines. Speech bubble has 3 simple raised teal abstract lines; source card has a folded corner and 3 teal abstract strokes, no text. Palette cream, pale mint, teal, warm yellow; matte soft clay-like material, gentle diffuse lighting, restrained reflection. Centered compact group, fully visible within central 75% of square canvas, empty margin around. CRITICAL: isolate the objects on real alpha transparency. Background pixels fully transparent; no checkerboard, no gray squares, no scenery, no floor, no backdrop, no background texture, no outline, no extra objects. No medical equipment or doctor clothes, no safety checkmark, no logos, letters or numerals. Deliver one RGBA image, no montage.
```
