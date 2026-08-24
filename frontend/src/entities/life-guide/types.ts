// REQ-CARE-004 / 노션 API 명세 13번 — 생활관리 가이드(LLM 결과)

export type RoutinePeriod = 'morning' | 'day' | 'evening';

export interface RoutineItem {
  period: RoutinePeriod;
  text: string;
  /** 복약 시간 설정값. 복약이 아닌 항목은 null */
  time: string | null;
}

export interface GuideSection {
  title: string;
  text: string;
}

export interface EmergencySigns {
  title: string;
  items: string[];
  action: string;
}

export interface RecordGuide {
  recordId: number;
  /** 이 안내가 어느 기록 기반인지. care_episodes.title */
  label: string;
  todayRoutine: RoutineItem[];
  sections: GuideSection[];
  emergencySigns: EmergencySigns;
}

export interface LifeGuide {
  records: RecordGuide[];
}
