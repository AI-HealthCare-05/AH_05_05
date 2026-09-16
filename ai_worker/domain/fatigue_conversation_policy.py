import re
from dataclasses import dataclass
from enum import StrEnum

from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy


class FatigueConversationDisposition(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    URGENT = "URGENT"


@dataclass(frozen=True)
class FatigueConversationDecision:
    disposition: FatigueConversationDisposition
    answer: str


class FatigueConversationPolicy:
    """피로 관련 질문을 제품 추천보다 안전한 문진으로 먼저 전환한다."""

    FOLLOW_UP_MARKER = "먼저 다음을 알려주시면 안전한 범위에서 일반 정보를 정리해 드릴 수 있습니다."
    LIFESTYLE_SECTION = "💬 **생활습관 확인**"

    _FATIGUE_PATTERN = re.compile(
        r"피곤|피로|기운\s*(?:없|이\s*없)|무기력|쉽게\s*지침",
    )
    _PAIN_PATTERN = re.compile(r"통증|두통|복통|요통|아프|아파|쑤시|쑤셔")

    def evaluate(self, question: str) -> FatigueConversationDecision | None:
        if not self._FATIGUE_PATTERN.search(question):
            return None
        if UrgentHealthSignalPolicy().evaluate(question):
            return FatigueConversationDecision(
                disposition=FatigueConversationDisposition.URGENT,
                answer=(
                    "피로와 함께 숨이 차거나 실신할 것 같은 증상처럼 급하게 확인해야 할 "
                    "신호가 있으면 즉시 119 또는 가까운 응급의료기관에 도움을 요청하세요."
                ),
            )
        # Pain requests use the symptom consultation gate, not supplement follow-up.
        if self._PAIN_PATTERN.search(question):
            return None
        return FatigueConversationDecision(
            disposition=FatigueConversationDisposition.FOLLOW_UP,
            answer=(f"{self.LIFESTYLE_SECTION}\n\n- 수면 시간과 식사, 음주 습관, 최근 생활 변화를 알려주세요."),
        )
