import re
from dataclasses import dataclass
from enum import StrEnum


class FatigueConversationDisposition(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    URGENT = "URGENT"


@dataclass(frozen=True)
class FatigueConversationDecision:
    disposition: FatigueConversationDisposition
    answer: str


class FatigueConversationPolicy:
    """피로 관련 질문을 제품 추천보다 안전한 문진으로 먼저 전환한다."""

    _FATIGUE_PATTERN = re.compile(
        r"피곤|피로|기운\s*(?:없|이\s*없)|무기력|쉽게\s*지침",
    )
    _URGENT_PATTERN = re.compile(
        r"흉통|가슴\s*통증|숨\s*(?:이\s*)?(?:차|가쁘)|호흡\s*곤란|"
        r"실신|의식\s*(?:저하|소실)|마비|검은\s*변|피\s*(?:를\s*)?토",
    )

    def evaluate(self, question: str) -> FatigueConversationDecision | None:
        if not self._FATIGUE_PATTERN.search(question):
            return None
        if self._URGENT_PATTERN.search(question):
            return FatigueConversationDecision(
                disposition=FatigueConversationDisposition.URGENT,
                answer=(
                    "피로와 함께 숨이 차거나 실신할 것 같은 증상처럼 급하게 확인해야 할 "
                    "신호가 있으면 즉시 119 또는 가까운 응급의료기관에 도움을 요청하세요."
                ),
            )
        return FatigueConversationDecision(
            disposition=FatigueConversationDisposition.FOLLOW_UP,
            answer=(
                "피로는 수면·식사·스트레스·현재 복용 제품 등 여러 요인과 관련될 수 있어 "
                "특정 제품을 바로 고르기는 어렵습니다.\n\n"
                "먼저 다음을 알려주시면 안전한 범위에서 일반 정보를 정리해 드릴 수 있습니다.\n"
                "- 피로가 시작된 시점과 지속 기간\n"
                "- 숨참, 흉통, 실신, 심한 어지러움 같은 급한 증상 여부\n"
                "- 현재 복용 중인 약과 영양제, 최근 추가·변경한 제품\n"
                "- 수면 시간, 식사·음주 습관, 최근 생활 변화\n\n"
                "증상이 지속되거나 일상생활에 영향을 주면 의료진과 상담해 원인을 확인하세요."
            ),
        )
