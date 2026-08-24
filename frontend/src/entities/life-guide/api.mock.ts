/**
 * 생활관리 가이드 목업. 환자1(김철수 · 우측 인공슬관절 전치환술) 1건입니다.
 *
 * `records` 가 2건 이상이면 화면이 기록별로 섹션을 분리해야 합니다 — 복약·일정과 달리
 * 생활관리는 진단에 종속되고 지침이 상충할 수 있어서입니다(무릎은 걷기 권장, 다른 질환은
 * 활동 제한). 그 경로를 눌러보려면 `mockLifeGuideTwoRecords()` 를 쓰세요.
 */
import type { LifeGuide } from './types';

export function mockLifeGuide(): LifeGuide {
  return {
    records: [
      {
        recordId: 12,
        label: '우측 인공슬관절 전치환술',
        todayRoutine: [
          { period: 'morning', text: '약 복용', time: '08:00' },
          { period: 'day', text: '무릎 굽힘·펴기 3세트', time: null },
          { period: 'evening', text: '보행기로 20분 걷기', time: null },
        ],
        sections: [
          { title: '식사·수분 관리', text: '단백질을 충분히 먹고 물을 자주 마셔주세요.' },
          {
            title: '운동·활동 관리',
            text: '보행기를 사용하고 계단과 무리한 회전을 피하세요.',
          },
          {
            title: '상처 관리',
            text: '수술 부위를 건조하게 유지하고 매일 상태를 확인해주세요.',
          },
        ],
        emergencySigns: {
          title: '즉시 연락할 증상',
          items: [
            '열 38℃ 이상',
            '수술 부위 붉어짐·고름',
            '종아리가 붓고 아픔',
            '갑작스러운 호흡곤란',
          ],
          action: '이 중 하나라도 있으면 즉시 병원에 연락하세요.',
        },
      },
    ],
  };
}

/**
 * 기록 2건 상태 — 섹션 분리가 제대로 되는지 확인할 때 `mockLifeGuide` 대신 씁니다.
 * 두 번째 기록은 지침이 상충하는 예(무릎은 걷기 권장, 심장은 활동 제한)로 뒀습니다.
 */
export function mockLifeGuideTwoRecords(): LifeGuide {
  const base = mockLifeGuide();
  return {
    records: [
      ...base.records,
      {
        recordId: 13,
        label: '심부전 입원 치료',
        todayRoutine: [
          { period: 'morning', text: '체중 재기', time: null },
          { period: 'day', text: '무리한 활동 피하기', time: null },
          { period: 'evening', text: '약 복용', time: '19:00' },
        ],
        sections: [
          { title: '수분·염분 관리', text: '물은 하루 1.5L 이내로, 짠 음식을 줄여주세요.' },
          { title: '활동 관리', text: '숨이 차면 바로 쉬고 무리한 운동은 피하세요.' },
        ],
        emergencySigns: {
          title: '즉시 연락할 증상',
          items: ['하루에 체중 1kg 이상 증가', '누우면 숨이 차는 증상', '발목이 심하게 부음'],
          action: '이 중 하나라도 있으면 즉시 병원에 연락하세요.',
        },
      },
    ],
  };
}
