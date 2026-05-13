from __future__ import annotations

from app.chat.models import ChatAnswer, ChatAnswerSection, EvidenceReference
from app.chat.utils import sanitize_chat_answer, sanitize_chat_text


def build_code_chat_answer(question: str, code_result) -> ChatAnswer:
    """
    Build a polished, evidence-grounded answer for code-snippet analysis.

    The output stays compact, but it adds structure so the response feels more
    deliberate than a raw summary dump.
    """
    q_lower = (question or "").lower()
    functions = _clean_list(getattr(code_result, "detected_functions", []))
    classes = _clean_list(getattr(code_result, "detected_classes", []))
    issues = _clean_list(getattr(code_result, "issues", []))
    improvements = _clean_list(getattr(code_result, "suggested_improvements", []))
    entrypoints = _clean_list(getattr(code_result, "entrypoints", []))
    imports = _clean_list(getattr(code_result, "imports", []))
    summary = sanitize_chat_text(getattr(code_result, "summary", ""), "")
    language = sanitize_chat_text(getattr(code_result, "language", ""), "snippet")
    confidence = getattr(code_result, "confidence", "medium")

    evidence = _build_evidence(code_result, confidence)
    evidence_ids = ["E1"] if evidence else []

    opening = _build_opening(
        q_lower=q_lower,
        summary=summary,
        language=language,
        functions=functions,
        classes=classes,
        issues=issues,
        improvements=improvements,
        entrypoints=entrypoints,
        imports=imports,
    )

    sections: list[ChatAnswerSection] = []
    confirmed_bullets = []
    if functions:
        confirmed_bullets.append(f"Functions: {', '.join(functions[:6])}.")
    if classes:
        confirmed_bullets.append(f"Classes or types: {', '.join(classes[:6])}.")
    if entrypoints:
        confirmed_bullets.append(f"Entry points: {', '.join(entrypoints[:4])}.")
    if imports:
        confirmed_bullets.append(f"Imports: {', '.join(imports[:4])}.")
    if summary:
        confirmed_bullets.append(summary)
    if confirmed_bullets:
        sections.append(
            ChatAnswerSection(
                title="What I can confirm",
                bullets=confirmed_bullets[:5],
                evidence_ids=evidence_ids,
            )
        )

    if issues:
        sections.append(
            ChatAnswerSection(
                title="Potential issues",
                bullets=issues[:4],
                evidence_ids=evidence_ids,
            )
        )

    if improvements or "improve" in q_lower:
        bullets = improvements[:4] if improvements else [
            "Add targeted tests around the main execution path.",
            "Strengthen error handling around edge cases.",
            "Keep the public surface small and explicit.",
        ]
        sections.append(
            ChatAnswerSection(
                title="Suggested improvements",
                bullets=bullets,
                evidence_ids=evidence_ids,
            )
        )

    if not sections:
        sections.append(
            ChatAnswerSection(
                title="Summary",
                content=summary or "The snippet is structurally small and only partially specified.",
                evidence_ids=evidence_ids,
            )
        )

    opening = f"In short: {opening}"
    if evidence:
        opening = f"{opening} See evidence [E1]."
    else:
        opening = f"{opening} The snippet does not provide enough grounded evidence for a stronger claim."

    return sanitize_chat_answer(
        ChatAnswer(
            answer=opening,
            short_answer=opening,
            sections=sections,
            confidence=confidence,
            evidence=evidence,
            warnings=list(getattr(code_result, "warnings", [])),
            insufficient_context=False,
            suggested_followups=[
                "What functions or classes are most important?",
                "Where are the main edge cases?",
                "What should be tested first?",
            ],
            used_llm=False,
            fallback_used=True,
        )
    )


def _build_opening(
    q_lower: str,
    summary: str,
    language: str,
    functions: list[str],
    classes: list[str],
    issues: list[str],
    improvements: list[str],
    entrypoints: list[str],
    imports: list[str],
) -> str:
    if "function" in q_lower and functions:
        return f"This snippet defines {', '.join(functions[:6])}."
    if "class" in q_lower and classes:
        return f"This snippet defines {', '.join(classes[:6])} as classes or types."
    if "issue" in q_lower or "production" in q_lower:
        if issues:
            return f"I can confirm these issues from the snippet: {'; '.join(issues[:4])}."
        return "No confirmed production blocker is visible from the snippet alone."
    if "improve" in q_lower:
        if improvements:
            return f"The strongest improvement opportunities are {'; '.join(improvements[:4])}."
        return "The main improvements here are clearer tests, tighter error handling, and simpler structure."

    if summary:
        return summary

    parts = [f"This {language or 'code'} snippet"]
    details = []
    if functions:
        details.append(f"defines {len(functions)} function{'s' if len(functions) != 1 else ''}")
    if classes:
        details.append(f"includes {len(classes)} class{'es' if len(classes) != 1 else ''}")
    if entrypoints:
        details.append(f"exposes entrypoints such as {', '.join(entrypoints[:3])}")
    if imports:
        details.append(f"depends on imports like {', '.join(imports[:3])}")
    if details:
        parts.append(", ".join(details))
    else:
        parts.append("only exposes limited structural signals")
    return " ".join(parts).strip().rstrip(".") + "."


def _build_evidence(code_result, confidence: str) -> list[EvidenceReference]:
    raw_evidence = list(getattr(code_result, "evidence", []) or [])
    if raw_evidence:
        evidence = []
        for item in raw_evidence[:3]:
            evidence.append(
                EvidenceReference(
                    source_type="file",
                    source_id=getattr(item, "source_id", "snippet"),
                    file=None,
                    reason=getattr(item, "reason", "Analyzed the submitted code snippet directly."),
                    snippet=getattr(item, "snippet", None),
                    confidence=confidence,
                )
            )
        return evidence

    return [
        EvidenceReference(
            source_type="file",
            source_id="snippet",
            file=None,
            reason="Analyzed the submitted code snippet directly.",
            snippet=None,
            confidence=confidence,
        )
    ]


def _clean_list(items) -> list[str]:
    result = []
    seen: set[str] = set()
    for item in items or []:
        cleaned = sanitize_chat_text(item, "")
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
