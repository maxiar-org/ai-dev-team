from dispatcher.models import Item
from dispatcher.prompts import build_prompt, dev_branch, slugify


def test_slugify_handles_accents_symbols_and_length():
    assert slugify("QR de WhatsApp: números argentinos (+54)") == "qr-de-whatsapp-numeros-argentinos-54"
    assert slugify("¡¡!!") == "tarea"
    assert len(slugify("a" * 100)) == 40
    assert dev_branch(3, "QR de WhatsApp") == "agent/3-qr-de-whatsapp"


def test_dev_prompt_includes_issue_branch_and_instruction(cfg):
    item = Item("qr-generator", 3, "issue", "QR de WhatsApp", "Normalizar +54", frozenset())
    text = build_prompt(cfg.roles_dir, "dev", item, "maxiar-org", "usa wa.me")
    assert "maxiar-org/qr-generator" in text and "#3" in text and "Normalizar +54" in text
    assert "agent/3-qr-de-whatsapp" in text and "usa wa.me" in text
    assert "Entregable visible" in text
    assert "{{" not in text


def test_review_prompt_uses_pr_branch_and_requires_verdict(cfg):
    item = Item("qr-generator", 7, "pr", "WA", "Closes #3", frozenset(), "agent/3-wa")
    text = build_prompt(cfg.roles_dir, "review", item, "maxiar-org")
    assert "agent/3-wa" in text
    assert "VEREDICTO: APROBADO" in text and "VEREDICTO: CAMBIOS" in text


def test_fix_prompt_without_instruction_says_so(cfg):
    item = Item("qr-generator", 7, "pr", "WA", "", frozenset(), "agent/3-wa")
    text = build_prompt(cfg.roles_dir, "fix", item, "maxiar-org")
    assert "(sin instrucciones adicionales)" in text and "agent/3-wa" in text


def test_user_text_with_braces_is_not_expanded(cfg):
    item = Item("qr-generator", 3, "issue", "T", "literal {{branch}}", frozenset())
    assert "literal {{branch}}" in build_prompt(cfg.roles_dir, "dev", item, "maxiar-org")


def test_qa_prompt_has_verdicts_and_evidence_branch(cfg):
    item = Item("qr-generator", 7, "pr", "WA", "Closes #3", frozenset(), "agent/3-wa")
    text = build_prompt(cfg.roles_dir, "qa", item, "maxiar-org")
    assert "QA: OK" in text and "QA: FALLA" in text and "QA: N/A" in text
    assert "qa-evidence" in text and "agent/3-wa" in text and "{{" not in text


def test_docs_prompt_mentions_starlight_and_pages(cfg):
    item = Item("ai-dev-team", 4, "issue", "Sitio de docs", "Crear el sitio", frozenset())
    text = build_prompt(cfg.roles_dir, "docs", item, "maxiar-org")
    assert "Starlight" in text and "GitHub Pages" in text and "/ai-dev-team/" in text
    assert "agent/4-sitio-de-docs" in text and "{{" not in text
