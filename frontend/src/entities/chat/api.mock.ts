/**
 * 챗봇 목업.
 *
 * 개인 출처(personal)에 페이지를 붙이지 않습니다. 원본 파일을 저장하지 않기로
 * 결정했으므로 개인 출처는 확정한 약봉투의 약 데이터를 가리킵니다.
 * 가짜 페이지 번호를 만들면 근거가 아니라 거짓이 됩니다.
 *
 * 근거 없는 응답 경로(`sources: []`)도 눌러볼 수 있어야 하므로, 질문에 "일반"·"보통"
 * 같은 말이 들어오면 근거 없는 답변을 돌려줍니다. 근거가 없는데 있는 것처럼 보이는 게
 * 이 서비스에서 가장 위험한 실패라, 그 상태를 개발 중에 반드시 확인해야 합니다.
 */
import type { SendChatPayload, SendChatResult } from './types';

const CONVERSATION_ID = 77;
let messageSeq = 1204;

/** 근거 없는 답변을 돌려줄 질문인지. 목업 전용 규칙입니다. */
function shouldAnswerWithoutSources(message: string): boolean {
  return /일반|보통|아무|그냥/.test(message);
}

export function mockSendChat(payload: SendChatPayload): SendChatResult {
  messageSeq += 1;

  if (shouldAnswerWithoutSources(payload.message)) {
    return {
      conversationId: payload.conversationId ?? CONVERSATION_ID,
      messageId: messageSeq,
      answer:
        '수술 후 회복 기간은 사람마다 달라서 일반적인 범위만 말씀드릴 수 있어요. '
        + '정확한 판단은 담당 의료진에게 확인해주세요.',
      sources: [],
    };
  }

  return {
    conversationId: payload.conversationId ?? CONVERSATION_ID,
    messageId: messageSeq,
    answer:
      '리바록사반을 복용하는 동안 잇몸이나 코피가 잘 멎지 않거나 이유 없이 멍이 크게 '
      + '들면 처방한 의료진에게 알려주세요.\n\n임의로 중단하지 마세요.',
    sources: [
      { scope: 'personal', title: '약봉투 · 리바록사반 10mg' },
      {
        scope: 'official',
        title: 'e약은요 · 리바록사반',
        organization: '식품의약품안전처',
        url: 'https://nedrug.mfds.go.kr',
      },
    ],
  };
}
