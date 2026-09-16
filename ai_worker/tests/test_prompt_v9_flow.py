import json

import pytest

from ai_worker.domain.medication_question_resolver import RuleBasedMedicationQuestionResolver
from ai_worker.domain.supplement_function_goal_detector import is_supplement_function_goal_question
from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy
from ai_worker.llm.generators.conversation_response_generator import (
    ConversationResponseGenerator,
    ConversationResponseInput,
)
from ai_worker.llm.prompts.medication_chat_prompt import build_medication_chat_messages
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import ConversationClassification
from ai_worker.schemas.enums import ChatRole
from ai_worker.schemas.knowledge import KnowledgeDocumentType, KnowledgeSectionType
from ai_worker.schemas.medication_chat import ActiveIntakeContext, MedicationChatRoute, MedicationGuideLookup
from ai_worker.tests.use_cases.test_answer_medication_question import (
    FakeKnowledgeRetriever,
    RecordingQueryPlanRetriever,
    StaticConversationGate,
    StaticConversationResponseGenerator,
    StaticExpressionCatalog,
    build_chunk,
    build_guide,
    build_request,
    build_use_case,
)


@pytest.mark.parametrize("question", ["숙면에 좋은 영양제", "잠 잘자기 위한 영양제", "눈에 좋은 영양제"])
def test_colloquial_supplement_goals_enter_evidence_search(question):
    assert is_supplement_function_goal_question(question)


@pytest.mark.parametrize(
    "question, urgent",
    [
        ("흉통은 없어요. 잠은 5시간 자요.", False),
        ("흉통이나 실신은 없어요.", False),
        ("흉통은 없지만 숨이 차요.", True),
        ("흉통이 있고 실신은 없어요.", True),
        ("숨이 잘 안 쉬어져요.", True),
        ("흉통이 없어지지 않아요.", True),
        ("흉통이 없다고 할 수 없어요.", True),
    ],
)
def test_current_positive_danger_is_not_confused_with_explicit_denial(question, urgent):
    assert UrgentHealthSignalPolicy().evaluate(question) is urgent


async def test_response_receives_bounded_same_session_history():
    class Client:
        messages = []

        async def ainvoke(self, messages):
            self.messages = messages
            return {"answer": "🌿 **일반 건강정보**\n\n- 일정한 수면 시간을 유지해 보세요."}

    client = Client()
    history = [ChatHistoryMessage(role=ChatRole.ASSISTANT, content=f"확인 질문 {i}") for i in range(6)]
    answer = await ConversationResponseGenerator(client=client).generate(
        ConversationResponseInput(
            question="일주일 전부터 피로하고 잠은 5시간 자요.",
            intent="GENERAL_HEALTH_FOLLOW_UP",
            recent_history=history,
        )
    )
    human = client.messages[-1].content
    assert "확인 질문 0" not in human
    assert "확인 질문 2" in human
    assert "확인 질문 5" in human
    assert "🌿 **일반 건강정보**" in answer
    assert "상호작용 확인" not in answer


async def test_first_fatigue_question_uses_conversation_response_without_fixed_preface():
    response = StaticConversationResponseGenerator(
        "💬 **생활습관 확인**\n\n- 수면 시간과 식사, 음주 습관, 최근 생활 변화를 알려주세요."
    )
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(conversation_response_generator=response, retriever=retriever).execute(
        build_request("피로회복에 좋은 영양제")
    )
    assert result.answer == ("💬 **생활습관 확인**\n\n- 수면 시간과 식사, 음주 습관, 최근 생활 변화를 알려주세요.")
    assert response.inputs[0].lifestyle_check_required is True
    assert retriever.received_kwargs is None


async def test_new_lifestyle_questionnaire_continues_without_legacy_preface():
    history = [
        ChatHistoryMessage(role=ChatRole.USER, content="피로회복에 좋은 영양제"),
        ChatHistoryMessage(
            role=ChatRole.ASSISTANT,
            content="💬 **생활습관 확인**\n\n- 식사와 수면 시간, 음주 습관, 최근 변화를 알려주세요.",
        ),
    ]
    result = await build_use_case(
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(intent="GENERAL_HEALTH_FOLLOW_UP", safety_signal="NONE", confidence="HIGH")
        ),
        conversation_response_generator=StaticConversationResponseGenerator(
            "🌿 **일반 건강정보**\n\n- 불규칙한 식사로 힘드셨겠어요. 규칙적인 식사를 챙겨보세요."
        ),
    ).execute(build_request("계속 피로하고 식사를 자주 걸러요").model_copy(update={"history": history}))
    assert "불규칙한 식사" in result.answer
    assert result.safety_reason_codes == ["GENERAL_HEALTH_FOLLOW_UP"]


@pytest.mark.parametrize("question", ["일주일 전부터 피로하고 잠은 5시간 자요.", "흉통은 없어요. 5시간 자요."])
async def test_fatigue_answers_continue_to_response_instead_of_repeating_questionnaire(question):
    # Use the real initial response so the follow-up exercises the production handoff.
    initial = await build_use_case().execute(build_request("피로회복에 좋은 영양제"))
    history = [ChatHistoryMessage(role=ChatRole.ASSISTANT, content=initial.answer)]
    retriever = RecordingQueryPlanRetriever()
    response = StaticConversationResponseGenerator("🌿 **일반 건강정보**\n\n- 일정한 수면 시간을 유지해 보세요.")
    result = await build_use_case(
        retriever=retriever,
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="GENERAL_HEALTH_FOLLOW_UP",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        conversation_response_generator=response,
    ).execute(build_request(question).model_copy(update={"history": history}))
    assert result.route is MedicationChatRoute.GENERAL_GUIDANCE
    assert result.safety_reason_codes == ["GENERAL_HEALTH_FOLLOW_UP"]
    assert "🌿 **일반 건강정보**" in result.answer
    assert response.inputs[0].recent_history == history
    assert retriever.received_kwargs is None


async def test_fatigue_follow_up_does_not_override_current_danger():
    initial = await build_use_case().execute(build_request("피로회복에 좋은 영양제"))
    result = await build_use_case().execute(
        build_request("피로하고 숨이 차요").model_copy(
            update={
                "history": [ChatHistoryMessage(role=ChatRole.ASSISTANT, content=initial.answer)],
            }
        )
    )
    assert result.route is MedicationChatRoute.RESTRICTED
    assert "119" in result.answer


async def test_new_named_product_after_fatigue_question_keeps_grounded_guide_route():
    initial = await build_use_case().execute(build_request("피로회복에 좋은 영양제"))
    response = StaticConversationResponseGenerator("unexpected general response")
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="MEDICATION_GUIDE",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        conversation_response_generator=response,
    ).execute(
        build_request("타이레놀 효능 알려줘").model_copy(
            update={
                "history": [ChatHistoryMessage(role=ChatRole.ASSISTANT, content=initial.answer)],
            }
        )
    )
    assert "통증" in result.answer
    assert "unexpected general response" not in result.answer
    assert response.inputs == []


@pytest.mark.parametrize(
    "question, goal",
    [
        ("숙면에 좋은 영양제", "수면의 질 개선"),
        ("잠 잘자기 위한 영양제", "수면의 질 개선"),
        ("눈에 좋은 영양제", "눈 건강"),
    ],
)
async def test_goal_questions_reach_source_backed_function_bullets(question, goal):
    base = build_chunk()
    chunk = base.model_copy(
        update={
            "content": f"시험 원료는 {goal}에 도움을 줄 수 있습니다.",
            "metadata": base.metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "section_type": KnowledgeSectionType.FUNCTION,
                    "ingredient_names": ["시험 원료"],
                }
            ),
        }
    )
    result = await build_use_case(
        retriever=FakeKnowledgeRetriever([chunk]),
        question_resolver=RuleBasedMedicationQuestionResolver(catalog=StaticExpressionCatalog([])),
    ).execute(build_request(question))
    assert result.route is MedicationChatRoute.SUPPLEMENT_GUIDE
    assert result.answer.startswith(f"**{goal} 관련 기능성 원료**")
    assert "💪🏻 **영양제 정보**" in result.answer
    assert f"- 시험 원료: {goal}에 도움을 줄 수 있음" in result.answer


@pytest.mark.parametrize("group", ["임신부", "수유부", "고령자", "간질환자", "신장질환자"])
async def test_goal_cautions_are_retrieved_for_only_the_grounded_ingredient(group):
    base = build_chunk()
    function = base.model_copy(
        update={
            "content": "시험 원료는 수면의 질 개선에 도움을 줄 수 있습니다.",
            "metadata": base.metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "section_type": KnowledgeSectionType.FUNCTION,
                    "ingredient_names": ["시험 원료"],
                }
            ),
        }
    )
    caution = function.model_copy(
        update={
            "point_id": "point-caution",
            "chunk_id": "c" * 64,
            "content": f"{group}는 섭취 전 전문가와 상담하십시오.",
            "metadata": function.metadata.model_copy(
                update={
                    "section_type": KnowledgeSectionType.CAUTION,
                    "content_hash": "c" * 64,
                    "document_id": "target-caution-document",
                }
            ),
        }
    )
    unrelated = caution.model_copy(
        update={
            "point_id": "point-other",
            "chunk_id": "d" * 64,
            "content": "다른 원료에만 적용되는 섭취 금지 조건입니다.",
            "metadata": caution.metadata.model_copy(
                update={
                    "ingredient_names": ["다른 원료"],
                    "content_hash": "d" * 64,
                    "document_id": "other-document",
                }
            ),
        }
    )

    class TargetedRetriever(FakeKnowledgeRetriever):
        async def search_with_diagnostics(self, *, execution_plan):
            # This test models DB retrieval: the caution query must name the known ingredient.
            is_caution_query = execution_plan.query_plan.section_types == [KnowledgeSectionType.CAUTION]
            chunks = [caution, unrelated] if is_caution_query else [function]
            if is_caution_query:
                assert execution_plan.query_plan.entity_names == ["시험 원료"]
                assert execution_plan.query_plan.interaction_pairs == []
            return await FakeKnowledgeRetriever(chunks).search_with_diagnostics(execution_plan=execution_plan)

    result = await build_use_case(
        retriever=TargetedRetriever(),
        question_resolver=RuleBasedMedicationQuestionResolver(catalog=StaticExpressionCatalog([])),
    ).execute(build_request("숙면에 좋은 영양제"))
    assert "⚠️ **주의사항**" in result.answer
    assert f"시험 원료: {group}는 섭취 전 전문가와 상담하십시오." in result.answer
    assert "다른 원료" not in result.answer
    assert KnowledgeSectionType.CAUTION in result.evidence_coverage.covered_section_types
    assert any(source.vector_chunk_id == "point-caution" for source in result.sources)
    assert all(source.vector_chunk_id != "point-other" for source in result.sources)


async def test_db_product_warnings_reach_answer_prompt_without_being_invented():
    guide = build_guide().model_copy(
        update={
            "pre_use_warning": "임부와 수유부는 복용 전 의사와 상담하십시오.",
            "precautions": "심한 간장애 환자는 복용하지 마십시오.",
        }
    )
    request = build_request("타이레놀 주의사항 알려줘")
    result = await build_use_case(lookup=MedicationGuideLookup(guide=guide)).execute(request)
    messages = build_medication_chat_messages(request=request, context=ActiveIntakeContext(user_id=1), result=result)
    payload = json.loads(str(messages[-1].content).split("\n", 1)[1])
    assert guide.pre_use_warning in payload["official_warning_texts"]
    assert guide.precautions in payload["official_warning_texts"]


@pytest.mark.parametrize("fails", [False, True])
async def test_caution_lookup_without_evidence_preserves_function_without_safety_claim(fails):
    base = build_chunk()
    function = base.model_copy(
        update={
            "content": "시험 원료는 눈 건강에 도움을 줄 수 있습니다.",
            "metadata": base.metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "section_type": KnowledgeSectionType.FUNCTION,
                    "ingredient_names": ["시험 원료"],
                }
            ),
        }
    )

    class Retriever(FakeKnowledgeRetriever):
        async def search_with_diagnostics(self, *, execution_plan):
            caution = execution_plan.query_plan.section_types == [KnowledgeSectionType.CAUTION]
            if caution and fails:
                raise TimeoutError("test-only unavailable DB")
            return await FakeKnowledgeRetriever([] if caution else [function]).search_with_diagnostics(
                execution_plan=execution_plan
            )

    result = await build_use_case(
        retriever=Retriever(),
        question_resolver=RuleBasedMedicationQuestionResolver(catalog=StaticExpressionCatalog([])),
    ).execute(build_request("눈에 좋은 영양제"))
    assert "시험 원료: 눈 건강에 도움" in result.answer
    assert "안전합니다" not in result.answer
    assert "임신부" not in result.answer
    assert result.evidence_coverage.covered_section_types == [KnowledgeSectionType.FUNCTION]


async def test_lifestyle_phase_is_rendered_into_actual_response_prompt():
    class Client:
        async def ainvoke(self, messages):
            assert "첫 생활습관 확인 필요: True" in messages[-1].content
            return {"answer": "💬 **생활습관 확인**\n\n- 수면과 식사 습관을 알려주세요."}

    answer = await ConversationResponseGenerator(client=Client()).generate(
        ConversationResponseInput(
            question="피로회복에 좋은 영양제",
            intent="GENERAL_HEALTH_FOLLOW_UP",
            lifestyle_check_required=True,
        )
    )
    assert answer.startswith("💬 **생활습관 확인**")


async def test_pain_after_lifestyle_question_keeps_consultation_route():
    result = await build_use_case(
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SYMPTOM_MEDICATION_GUIDANCE",
                symptom_context="머리가 아파요",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        question_resolver=RuleBasedMedicationQuestionResolver(catalog=StaticExpressionCatalog([])),
    ).execute(
        build_request("머리가 아파요").model_copy(
            update={
                "history": [
                    ChatHistoryMessage(
                        role=ChatRole.ASSISTANT, content="💬 **생활습관 확인**\n\n- 수면 시간을 알려주세요."
                    ),
                ]
            }
        )
    )
    assert result.route is MedicationChatRoute.CLARIFICATION
    assert "상담" in result.answer
    assert "성분을 추천" not in result.answer


async def test_fatigue_with_pain_does_not_start_a_supplement_questionnaire():
    result = await build_use_case(
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SYMPTOM_MEDICATION_GUIDANCE",
                symptom_context="피곤하고 머리가 아파요",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        question_resolver=RuleBasedMedicationQuestionResolver(catalog=StaticExpressionCatalog([])),
    ).execute(build_request("피곤하고 머리가 아파요"))
    assert result.route is MedicationChatRoute.CLARIFICATION
    assert "상담" in result.answer
    assert "생활습관 확인" not in result.answer
