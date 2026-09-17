from ai_worker.core.config import Config


def test_report_rag_enabled_without_environment_setting(monkeypatch):
    monkeypatch.delenv("INTAKE_REPORT_RAG_ENABLED", raising=False)
    assert Config(_env_file=None).INTAKE_REPORT_RAG_ENABLED is True


def test_report_rag_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("INTAKE_REPORT_RAG_ENABLED", "false")
    assert Config(_env_file=None).INTAKE_REPORT_RAG_ENABLED is False
