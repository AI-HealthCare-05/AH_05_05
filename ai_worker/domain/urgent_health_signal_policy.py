import re


class UrgentHealthSignalPolicy:
    """LLM 장애와 무관하게 긴급 도움을 우선해야 하는 건강 신호만 감지한다."""

    _PATTERN = re.compile(
        r"흉통|가슴\s*(?:이\s*)?(?:아프|통증)|"
        r"숨\s*(?:이\s*)?(?:차|가쁘|(?:잘\s*)?안\s*쉬)|호흡\s*곤란|"
        r"실신|의식\s*(?:저하|소실)|마비|검은\s*변|피\s*(?:를\s*)?토|"
        r"(?:입술|혀|얼굴)\s*(?:이\s*)?(?:붓|부어)|"
        r"(?:온몸|전신)\s*(?:에\s*)?두드러기",
    )

    _EXPLICIT_DENIAL = re.compile(
        rf"(?:\s*(?:이나|나|와|과|,|·)\s*(?:{_PATTERN.pattern}))*"
        r"\s*(?:은|는|이|가|도)?\s*없(?:어요|습니다|고|지만|음|다|어)(?=$|[\s.,!?])"
    )

    def evaluate(self, question: str) -> bool:
        # 명시적인 부정만 제외하며, 이웃한 실제 위험 증상은 계속 감지한다.
        return any(not self._EXPLICIT_DENIAL.match(question, match.end()) for match in self._PATTERN.finditer(question))
