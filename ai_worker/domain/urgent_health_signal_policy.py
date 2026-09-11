import re


class UrgentHealthSignalPolicy:
    """LLM 장애와 무관하게 긴급 도움을 우선해야 하는 건강 신호만 감지한다."""

    _PATTERN = re.compile(
        r"흉통|가슴\s*(?:이\s*)?(?:아프|통증)|"
        r"숨\s*(?:이\s*)?(?:차|가쁘|(?:잘\s*)?안\s*쉬)|호흡\s*곤란|"
        r"실신|의식\s*(?:저하|소실)|마비|검은\s*변|피\s*(?:를\s*)?토",
    )

    def evaluate(self, question: str) -> bool:
        return self._PATTERN.search(question) is not None
