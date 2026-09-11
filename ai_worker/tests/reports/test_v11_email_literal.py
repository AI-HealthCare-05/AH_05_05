from app.core.email.markdown_renderer import render_safe_markdown


def test_entity_encoded_card_text_stays_literal_without_invented_links_or_html() -> None:
    rendered = str(render_safe_markdown(
        "## 약 정보\n\n"
        "&#91;등록명&#93;&#40;https://not-a-source.example&#41; "
        "&#42;&#42;강조 아님&#42;&#42; &lt;img src=x onerror=alert(1)&gt;"
    ))
    assert "[등록명](https://not-a-source.example)" in rendered
    assert "**강조 아님**" in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "<a " not in rendered and "<img " not in rendered and "<strong>" not in rendered


def test_trusted_template_markdown_still_renders_links_and_bold() -> None:
    rendered = str(render_safe_markdown("**주의** · [공공 안내](https://example.org/guide)"))
    assert "<strong>주의</strong>" in rendered
    assert '<a href="https://example.org/guide"' in rendered


def test_entity_encoded_entity_remains_literal_after_one_decode() -> None:
    rendered = str(render_safe_markdown("원문: &amp;lt;script&amp;gt;"))
    assert "원문: &amp;lt;script&amp;gt;" in rendered
