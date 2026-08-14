"""
OCR-RAG-LLM 파이프라인 검증용 가상 진료문서 생성기
- 환자 2명 × (퇴원기록지 / 약봉투 / 복약지도서)
- 각 문서마다 clean(깔끔) / rough(그늘·기울어짐·일부 잘림) 두 버전
※ 모든 내용은 테스트용 가상 데이터. 실제 환자 정보 아님.

이 스크립트는 프로젝트 의존성에 포함되지 않은 패키지를 씁니다. 돌리려면 따로 설치하세요.
    pip install pillow numpy
그리고 한글 렌더링에 Noto Sans CJK KR 이 필요합니다(Ubuntu: fonts-noto-cjk).

이미 생성된 이미지가 같은 폴더에 있으므로 보통은 실행할 필요가 없습니다.
테스트 케이스를 추가하고 싶을 때만 아래 JOBS 와 문서 내용을 고쳐 다시 돌리세요.
"""

import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

random.seed(7)
np.random.seed(7)

OUT = os.path.dirname(os.path.abspath(__file__))
FR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FB = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
KR = 1  # ttc index: Korean


def f(size, bold=False):
    return ImageFont.truetype(FB if bold else FR, size, index=KR)


W, H = 1240, 1754  # A4 @150dpi
M = 96  # margin


# ────────────────────────── 렌더러 ──────────────────────────
def wrap(draw, text, font, maxw):
    out, line = [], ""
    for ch in text:
        if ch == "\n":
            out.append(line)
            line = ""
            continue
        t = line + ch
        if draw.textlength(t, font=font) > maxw and line:
            out.append(line)
            line = ch
        else:
            line = t
    out.append(line)
    return out


def render(blocks, page_note=None, w=W, h=H, margin=M):  # noqa: C901  블록 종류별 분기 체인
    img = Image.new("RGB", (w, h), (252, 252, 250))
    d = ImageDraw.Draw(img)
    x, y = margin, margin
    maxw = w - margin * 2

    for kind, text in blocks:
        if kind == "hospital":
            d.text((x, y), text, font=f(21), fill=(70, 70, 70))
            y += 30
        elif kind == "h1":
            d.text((x, y), text, font=f(40, True), fill=(15, 15, 15))
            y += 56
            d.line([(x, y), (x + maxw, y)], fill=(40, 40, 40), width=3)
            y += 22
        elif kind == "meta":
            d.text((x, y), text, font=f(20), fill=(45, 45, 45))
            y += 29
        elif kind == "rule":
            y += 6
            d.line([(x, y), (x + maxw, y)], fill=(200, 200, 200), width=1)
            y += 16
        elif kind == "section":
            y += 12
            d.text((x, y), text, font=f(24, True), fill=(20, 20, 20))
            y += 38
        elif kind == "body":
            for ln in wrap(d, text, f(20), maxw):
                d.text((x, y), ln, font=f(20), fill=(30, 30, 30))
                y += 30
        elif kind == "bullet":
            for i, ln in enumerate(wrap(d, text, f(20), maxw - 26)):
                d.text((x + (6 if i == 0 else 26), y), ("- " if i == 0 else "") + ln, font=f(20), fill=(30, 30, 30))
                y += 30
        elif kind == "mono":
            d.text((x + 6, y), text, font=f(20), fill=(25, 25, 25))
            y += 29
        elif kind == "spacer":
            y += int(text)
    # 직인
    cx, cy, r = w - margin - 62, h - margin - 62, 58
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(190, 55, 45), width=4)
    d.text((cx - 40, cy - 26), "병원장", font=f(21, True), fill=(190, 55, 45))
    d.text((cx - 25, cy + 4), "직인", font=f(21, True), fill=(190, 55, 45))
    if page_note:
        d.text((w // 2 - 40, h - 52), page_note, font=f(18), fill=(120, 120, 120))
    return img


def render_bag(blocks):  # noqa: C901  블록 종류별 분기 체인
    """약봉투 — 세로로 긴 봉투 라벨 느낌"""
    w, h = 900, 1400
    img = Image.new("RGB", (w, h), (255, 253, 244))
    d = ImageDraw.Draw(img)
    d.rectangle([26, 26, w - 26, h - 26], outline=(150, 150, 140), width=3)
    for xx in range(40, w - 40, 18):  # 점선 (봉투 절취선)
        d.line([(xx, 62), (xx + 9, 62)], fill=(170, 170, 160), width=2)
    x, y = 62, 92
    maxw = w - 124
    for kind, text in blocks:
        if kind == "h1":
            d.text((x, y), text, font=f(34, True), fill=(20, 20, 20))
            y += 50
        elif kind == "meta":
            d.text((x, y), text, font=f(19), fill=(50, 50, 50))
            y += 27
        elif kind == "rule":
            y += 8
            d.line([(x, y), (x + maxw, y)], fill=(190, 190, 180), width=2)
            y += 16
        elif kind == "timebox":
            d.rectangle([x, y, x + maxw, y + 40], fill=(238, 236, 222), outline=(170, 170, 155), width=2)
            d.text((x + 12, y + 8), text, font=f(22, True), fill=(30, 30, 30))
            y += 52
        elif kind == "mono":
            d.text((x + 14, y), text, font=f(20), fill=(25, 25, 25))
            y += 30
        elif kind == "body":
            for ln in wrap(d, text, f(19), maxw):
                d.text((x, y), ln, font=f(19), fill=(45, 45, 45))
                y += 27
        elif kind == "spacer":
            y += int(text)
    return img


# ────────────────────────── 열화(그늘·기울어짐·잘림) ──────────────────────────
def degrade(img, seed=0, crop_side="right"):
    rnd = random.Random(seed)
    im = img.convert("RGB")
    w, h = im.size

    # 1) 원근 왜곡 (책상에 놓고 비스듬히 촬영한 느낌)
    dx = int(w * rnd.uniform(0.012, 0.022))
    dy = int(h * rnd.uniform(0.004, 0.010))
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(dx, dy), (w - int(dx * 0.4), 0), (w - dx, h - dy), (int(dx * 0.5), h)]

    def coeffs(pa, pb):
        mat = []
        for p1, p2 in zip(pa, pb, strict=True):
            mat.append([p2[0], p2[1], 1, 0, 0, 0, -p1[0] * p2[0], -p1[0] * p2[1]])
            mat.append([0, 0, 0, p2[0], p2[1], 1, -p1[1] * p2[0], -p1[1] * p2[1]])
        mat_a = np.matrix(mat, dtype=float)
        vec_b = np.array(pa).reshape(8)
        return np.array(np.dot(np.linalg.inv(mat_a.T * mat_a) * mat_a.T, vec_b)).reshape(8)

    im = im.transform((w, h), Image.PERSPECTIVE, coeffs(src, dst), Image.BICUBIC, fillcolor=(246, 246, 244))

    # 2) 약간 회전
    im = im.rotate(rnd.uniform(-2.4, -1.1), resample=Image.BICUBIC, expand=False, fillcolor=(246, 246, 244))

    # 3) 그늘 — 한쪽 모서리에서 번지는 어두운 그라디언트 + 손/몸 그림자
    a = np.asarray(im).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    corner = rnd.choice([(0, 0), (w, 0), (0, h)])
    dist = np.sqrt((xx - corner[0]) ** 2 + (yy - corner[1]) ** 2)
    dist = dist / dist.max()
    shade = 0.55 + 0.45 * np.clip(dist * rnd.uniform(1.5, 2.1), 0, 1)  # 0.55~1.0
    band_c = rnd.uniform(0.15, 0.4) * w
    band = 1.0 - 0.28 * np.exp(-((xx - band_c) ** 2) / (2 * (w * 0.13) ** 2))
    mask = np.clip(shade * band, 0.35, 1.0)[..., None]
    a = a * mask

    # 4) 조명 얼룩 + 노이즈
    a += np.random.normal(0, 3.2, a.shape)
    a = np.clip(a, 0, 255).astype(np.uint8)
    im = Image.fromarray(a)

    # 5) 초점 약간 흐림
    im = im.filter(ImageFilter.GaussianBlur(rnd.uniform(0.5, 0.9)))

    # 6) 일부 잘림 (촬영 시 프레임 밖으로 나간 상황)
    cut = rnd.uniform(0.06, 0.10)
    if crop_side == "right":
        im = im.crop((0, 0, int(w * (1 - cut)), h))
    elif crop_side == "bottom":
        im = im.crop((0, 0, w, int(h * (1 - cut))))
    else:
        im = im.crop((int(w * cut), 0, w, h))
    return im


def save(img, name, quality=None):
    path = os.path.join(OUT, name)
    if name.endswith(".jpg"):
        img.save(path, "JPEG", quality=quality or 88, subsampling=2)
    else:
        img.save(path)
    print("saved", name, img.size)


# ══════════════════════════ 환자 1 · 영문 약어 위주 ══════════════════════════
P1_DISCHARGE = [
    ("hospital", "한빛대학교병원  Hanbit University Hospital"),
    ("h1", "퇴원기록지  Discharge Summary"),
    ("meta", "등록번호 20260731-0142        성명 김철수 (M/72)"),
    ("meta", "입원일 2026-07-31             퇴원일 2026-08-07"),
    ("meta", "진료과 정형외과(OS)           주치의 박준혁"),
    ("rule", ""),
    ("section", "진단 및 수술"),
    ("mono", "Dx.  Rt Femur head Fracture, closed"),
    ("mono", "Op.  Rt Femur head ORIF  (2026-08-01)"),
    ("mono", "Anesth.  G/A"),
    ("section", "경과 요약"),
    ("bullet", "Adm. 후 f/u X-ray 및 CT 상 Rt femoral head Fx 확인, POD#1 ORIF 시행"),
    ("bullet", "POD#3 PT 시작, WBAT with walker. V/S stable, wound clean & dry, no s/o infection"),
    ("bullet", "Hb 11.2 → 10.8 g/dL, transfusion 없이 f/u. POD#7 stitch out 후 discharge"),
    ("section", "퇴원 시 처방"),
    ("mono", "Celecoxib 200mg      1 cap   bid   po   7일"),
    ("mono", "Rivaroxaban 10mg     1 tab   qd    po   14일"),
    ("mono", "Acetaminophen 650mg  1 tab   prn   po   (max tid, 6h 간격)"),
    ("mono", "Famotidine 20mg      1 tab   bid   po   7일"),
    ("section", "운동 및 재활"),
    ("bullet", "보행: walker 사용하여 실내 보행 1일 3회, 회당 10~20분"),
    ("bullet", "Ankle pumping 시간당 10회 / Quadriceps setting 10회 3set 1일"),
    ("bullet", "체중부하: WBAT (통증 허용 범위 내 부분 체중부하)"),
    ("section", "생활습관"),
    ("bullet", "고단백 식이 유지, 수분 1일 1.5L 이상 섭취"),
    ("bullet", "금연, 금주"),
    ("bullet", "낙상 예방: 야간 조명, 화장실 손잡이, 미끄럼 방지 매트"),
    ("section", "금기사항  Contraindication"),
    ("bullet", "고관절 90도 이상 굴곡 금지"),
    ("bullet", "다리 교차(cross leg) 및 내회전 금지"),
    ("bullet", "낮은 의자, 낮은 변기 사용 금지"),
    ("bullet", "계단 및 쪼그려 앉기 금지 (4주간)"),
    ("section", "외래 예약"),
    ("mono", "2026-08-14  10:30   정형외과(OS) 박준혁    본관 2층"),
    ("mono", "2026-08-21  14:00   재활의학과 운동교육    재활센터 1층"),
    ("section", "응급 시 연락"),
    (
        "body",
        "38℃ 이상 발열, 수술창 발적·삼출, 종아리 부종·통증, 갑작스러운 호흡곤란 시 "
        "즉시 응급실 내원 또는 02-000-0000 (24시간)",
    ),
]

P1_BAG = [
    ("h1", "조제약 봉투"),
    ("meta", "한빛대학교병원 약제부"),
    ("meta", "김철수  등록번호 20260731-0142"),
    ("meta", "조제일 2026-08-07     7일분 / 총 14포"),
    ("rule", ""),
    ("timebox", "아침 식후 30분"),
    ("mono", "Celecoxib 200mg        1 캡슐"),
    ("mono", "Famotidine 20mg        1 정"),
    ("spacer", "10"),
    ("timebox", "저녁 식후 30분"),
    ("mono", "Celecoxib 200mg        1 캡슐"),
    ("mono", "Famotidine 20mg        1 정"),
    ("mono", "Rivaroxaban 10mg       1 정"),
    ("spacer", "10"),
    ("timebox", "통증 시 (필요할 때만)"),
    ("mono", "Acetaminophen 650mg    1 정"),
    ("mono", "1일 최대 3회, 6시간 이상 간격"),
    ("rule", ""),
    ("body", "· 임의로 복용을 중단하지 마세요."),
    ("body", "· 리바록사반은 14일분입니다. 남은 약이 있어도 처방일수를 지켜주세요."),
    ("body", "· 문의: 약제부 02-000-0000 (평일 09:00~17:00)"),
]

P1_GUIDE = [
    ("hospital", "한빛대학교병원 약제부"),
    ("h1", "복약지도서"),
    ("meta", "성명 김철수        조제일 2026-08-07        7일분"),
    ("rule", ""),
    ("section", "1. 세레콕시브 200mg (소염진통제)"),
    ("bullet", "1일 2회, 아침·저녁 식후 30분에 1캡슐"),
    ("bullet", "수술 부위의 통증과 염증을 줄여줍니다"),
    ("bullet", "속쓰림, 검은 변, 얼굴·다리 부종이 생기면 알려주세요"),
    ("section", "2. 리바록사반 10mg (항응고제)"),
    ("bullet", "1일 1회 저녁 식후 1정, 14일간 복용"),
    ("bullet", "수술 후 다리 혈관에 피가 굳는 것(혈전)을 예방합니다"),
    ("bullet", "잇몸·코피가 멎지 않거나 이유 없이 멍이 크게 들면 즉시 연락하세요"),
    ("bullet", "임의로 중단하지 마세요. 치과 치료나 다른 수술 전에는 반드시 알리세요"),
    ("section", "3. 아세트아미노펜 650mg (해열진통제)"),
    ("bullet", "통증이 있을 때만 1정, 1일 최대 3회까지"),
    ("bullet", "복용 간격은 6시간 이상 유지하세요"),
    ("bullet", "다른 감기약과 함께 먹으면 성분이 겹칠 수 있어 확인이 필요합니다"),
    ("section", "4. 파모티딘 20mg (위산 억제제)"),
    ("bullet", "1일 2회, 아침·저녁 식후 1정"),
    ("bullet", "진통제로 인한 위 자극을 줄여줍니다"),
    ("section", "공통 주의사항"),
    ("bullet", "복용 중 술은 피하세요"),
    ("bullet", "약을 거른 경우 다음 복용 시간에 1회분만 드세요. 두 배로 드시면 안 됩니다"),
    ("bullet", "다른 병원·약국에서 약을 받을 때 이 지도서를 보여주세요"),
]

# ══════════════════════════ 환자 2 · 한글 위주, 퇴원기록지 2장 ══════════════════════════
P2_D1 = [
    ("hospital", "한빛대학교병원  Hanbit University Hospital"),
    ("h1", "퇴원기록지  (1/2)"),
    ("meta", "등록번호 20260803-0577        성명 이영자 (F/58)"),
    ("meta", "입원일 2026-08-03             퇴원일 2026-08-09"),
    ("meta", "진료과 흉부외과               주치의 정민서"),
    ("rule", ""),
    ("section", "진단 및 수술"),
    ("body", "진단명 : 갈비뼈 골절 (우측 5·6·7번 다발성)"),
    ("body", "수술명 : 늑골 골절 관혈적 정복 및 금속판 내고정술 (2026-08-04)"),
    ("body", "마취 : 전신마취"),
    ("section", "입원 경과"),
    ("bullet", "낙상으로 내원, 흉부 CT에서 우측 5~7번 갈비뼈 골절 및 경미한 혈흉 확인"),
    ("bullet", "입원 2일째 금속판 고정 수술 시행, 수술 중 특이 소견 없었습니다"),
    ("bullet", "수술 다음 날부터 심호흡 운동과 보행을 시작했고 통증은 조절되는 상태입니다"),
    ("bullet", "흉관은 수술 3일째 제거하였고 이후 흉부 X선에서 폐 확장 양호합니다"),
    ("bullet", "발열이나 감염 소견 없이 안정적으로 회복하여 퇴원합니다"),
    ("section", "퇴원 시 처방  (7일분)"),
    ("mono", "아세트아미노펜 650mg   1정   1일 3회   식후"),
    ("mono", "트라마돌 50mg          1정   1일 2회   아침·저녁 식후"),
    ("mono", "암브록솔 30mg          1정   1일 3회   식후"),
    ("mono", "파모티딘 20mg          1정   1일 2회   아침·저녁 식후"),
    ("section", "검사 결과 요약"),
    ("mono", "혈색소       11.6 g/dL      백혈구   7,100 /uL"),
    ("mono", "C반응단백    1.8 mg/dL      체온     36.7 ℃"),
    ("mono", "흉부 X선     우측 폐 확장 양호, 잔여 혈흉 소량"),
]

P2_D2 = [
    ("hospital", "한빛대학교병원  Hanbit University Hospital"),
    ("h1", "퇴원기록지  (2/2)"),
    ("meta", "등록번호 20260803-0577        성명 이영자 (F/58)"),
    ("rule", ""),
    ("section", "호흡 운동 (가장 중요합니다)"),
    ("bullet", "심호흡 운동: 깊게 들이마시고 3초 참았다가 천천히 내쉬기. 1시간에 10회"),
    ("bullet", "호흡 운동기(볼 3개)를 사용하는 경우 1시간에 10회씩 하세요"),
    ("bullet", "기침할 때는 베개나 수건을 가슴에 대고 감싸 안으면 통증이 줄어듭니다"),
    ("bullet", "아프다고 얕게 숨쉬면 폐렴이 생길 수 있습니다. 통증약을 드시고 꼭 하세요"),
    ("section", "일상생활"),
    ("bullet", "보행: 하루 3~4회, 회당 10~15분 실내 보행부터 시작"),
    ("bullet", "수면: 등을 받쳐 상체를 약간 세운 자세가 편합니다"),
    ("bullet", "샤워: 수술 부위 실밥 제거 후(퇴원 5일째 외래) 가능합니다"),
    ("bullet", "식사: 단백질을 충분히 드시고 수분을 자주 섭취하세요"),
    ("bullet", "금연은 반드시 필요합니다. 흡연은 폐 합병증과 골 유합 지연을 유발합니다"),
    ("section", "금기사항"),
    ("bullet", "무거운 물건 들기 금지 (4~6주간, 5kg 이상)"),
    ("bullet", "상체를 비틀거나 갑자기 젖히는 동작 금지"),
    ("bullet", "팔을 어깨보다 높이 반복해서 올리는 동작 금지"),
    ("bullet", "운전 금지 (통증약 복용 중, 최소 3주)"),
    ("bullet", "음주 금지 (통증약과 함께 복용 시 위험합니다)"),
    ("section", "외래 예약"),
    ("mono", "2026-08-14  09:40   흉부외과 정민서       본관 3층   실밥 제거"),
    ("mono", "2026-08-28  11:00   흉부외과 정민서       본관 3층   흉부 X선 확인"),
    ("section", "이런 증상이 있으면 즉시 병원에 오세요"),
    ("bullet", "38℃ 이상의 열이 나거나 오한이 있을 때"),
    ("bullet", "숨쉬기가 갑자기 힘들어지거나 가슴 통증이 심해질 때"),
    ("bullet", "수술 부위가 붉게 부어오르거나 고름이 나올 때"),
    ("bullet", "가래에 피가 섞여 나올 때"),
    ("body", "응급 연락처 : 02-000-0000 (24시간 응급실)"),
]

P2_BAG = [
    ("h1", "조제약 봉투"),
    ("meta", "한빛대학교병원 약제부"),
    ("meta", "이영자  등록번호 20260803-0577"),
    ("meta", "조제일 2026-08-09     7일분 / 총 21포"),
    ("rule", ""),
    ("timebox", "아침 식후 30분"),
    ("mono", "아세트아미노펜 650mg    1정"),
    ("mono", "트라마돌 50mg           1정"),
    ("mono", "암브록솔 30mg           1정"),
    ("mono", "파모티딘 20mg           1정"),
    ("spacer", "8"),
    ("timebox", "점심 식후 30분"),
    ("mono", "아세트아미노펜 650mg    1정"),
    ("mono", "암브록솔 30mg           1정"),
    ("spacer", "8"),
    ("timebox", "저녁 식후 30분"),
    ("mono", "아세트아미노펜 650mg    1정"),
    ("mono", "트라마돌 50mg           1정"),
    ("mono", "암브록솔 30mg           1정"),
    ("mono", "파모티딘 20mg           1정"),
    ("rule", ""),
    ("body", "· 트라마돌 복용 후 졸음·어지러움이 있을 수 있습니다. 운전하지 마세요."),
    ("body", "· 술과 함께 복용하지 마세요."),
    ("body", "· 문의: 약제부 02-000-0000"),
]

P2_GUIDE = [
    ("hospital", "한빛대학교병원 약제부"),
    ("h1", "복약지도서"),
    ("meta", "성명 이영자        조제일 2026-08-09        7일분"),
    ("rule", ""),
    ("section", "1. 아세트아미노펜 650mg (해열진통제)"),
    ("bullet", "1일 3회, 매 식후 1정"),
    ("bullet", "갈비뼈 통증을 줄여 숨을 깊게 쉴 수 있게 도와줍니다"),
    ("bullet", "다른 감기약·진통제와 성분이 겹칠 수 있으니 함께 드시기 전에 확인하세요"),
    ("section", "2. 트라마돌 50mg (중등도 진통제)"),
    ("bullet", "1일 2회, 아침·저녁 식후 1정"),
    ("bullet", "아세트아미노펜만으로 조절되지 않는 통증에 사용합니다"),
    ("bullet", "졸음, 어지러움, 메스꺼움이 있을 수 있습니다. 운전은 하지 마세요"),
    ("bullet", "변비가 생기기 쉬우니 물과 채소를 충분히 드세요"),
    ("section", "3. 암브록솔 30mg (거담제)"),
    ("bullet", "1일 3회, 매 식후 1정"),
    ("bullet", "가래를 묽게 만들어 기침으로 배출하기 쉽게 합니다"),
    ("bullet", "심호흡 운동과 함께 하시면 폐렴 예방에 도움이 됩니다"),
    ("section", "4. 파모티딘 20mg (위산 억제제)"),
    ("bullet", "1일 2회, 아침·저녁 식후 1정"),
    ("bullet", "진통제로 인한 위 자극을 줄여줍니다"),
    ("section", "공통 주의사항"),
    ("bullet", "복용 중 술은 절대 피하세요 (트라마돌과 함께 복용 시 위험합니다)"),
    ("bullet", "약을 거른 경우 다음 시간에 1회분만 드세요"),
    ("bullet", "통증이 조절되지 않으면 임의로 늘리지 말고 병원에 연락하세요"),
]

# ────────────────────────── 실행 ──────────────────────────
JOBS = [
    ("p1_01_discharge", render(P1_DISCHARGE, "1 / 1"), "right"),
    ("p1_02_medbag", render_bag(P1_BAG), "right"),
    ("p1_03_medguide", render(P1_GUIDE, "1 / 1"), "bottom"),
    ("p2_01_discharge_p1", render(P2_D1, "1 / 2"), "right"),
    ("p2_02_discharge_p2", render(P2_D2, "2 / 2"), "bottom"),
    ("p2_03_medbag", render_bag(P2_BAG), "left"),
    ("p2_04_medguide", render(P2_GUIDE, "1 / 1"), "right"),
]

for i, (name, img, side) in enumerate(JOBS):
    save(img, f"{name}_clean.jpg", quality=92)
    save(degrade(img, seed=i * 13 + 5, crop_side=side), f"{name}_rough.jpg", quality=62)

print("\n총", len(JOBS) * 2, "장 생성")
