// REQ-CHAT-001 / 노션 API 명세 15번 — RAG 챗봇
//
// 이 화면의 존재 이유는 출처 표시입니다. 복약 안내 화면에서 출처를 빼기로 정했으므로
// (명세 11번) 공공 근거를 화면에서 보여줄 수 있는 곳이 여기뿐입니다.

export type SourceScope = 'personal' | 'official';

export interface ChatSource {
  scope: SourceScope;
  /** personal — 확정 환자 데이터. 예: '퇴원요약지 · 의료진 권고사항' */
  /** official — 공공자료. 예: 'e약은요 · 셀레콕시브' */
  title: string;
  /** official 일 때만. 발행 기관 */
  organization?: string | null;
  /** official 일 때만. 원문 링크 */
  url?: string | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  /** assistant 메시지의 근거. user 메시지는 빈 배열 */
  sources: ChatSource[];
}

export interface SendChatPayload {
  /** 세션을 시작한 기록. 없으면 null */
  recordId: number | null;
  message: string;
  /** 기존 세션 이어가기. 첫 질문이면 null */
  conversationId: number | null;
}

export interface SendChatResult {
  conversationId: number;
  messageId: number;
  answer: string;
  sources: ChatSource[];
}
