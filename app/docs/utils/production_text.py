import re

from app.docs.utils.evidence_sanitizer import sanitize_text

_IGNORED_TOKENS = [
    "node_modules",
    ".venv",
    "site-packages",
    "__pycache__",
    "pip/_vendor",
    "MagicMock",
    "<Mock",
    "type='",
    "confidence='",
    "reasoning=[",
    "evidence=[",
    "EvidenceItem(",
    "ArchitectureResult(",
]

def _append_low_confidence(parts: list[str], confidence: str) -> list[str]:
    if confidence == "low":
        parts.append("This summary is based on limited evidence.")
    return parts

def _sanitize_text(value) -> str:
    text = sanitize_text(value, fallback="")
    for token in _IGNORED_TOKENS:
        text = text.replace(token, "")
    return re.sub(r"\s+", " ", text).strip()

def clean_sentence(text: str) -> str:
    """Normalize whitespace and ensure capitalization and punctuation."""
    if not text:
        return "Insufficient evidence from codebase."
    text = _sanitize_text(text)
    if not text:
        return "Insufficient evidence from codebase."
    if len(text) > 0 and text[0].islower():
        text = text[0].upper() + text[1:]
    if not text.endswith(('.', '!', '?')):
        text += '.'
    return text

def clean_list(items: list, max_items: int = 6) -> list[str]:
    """Deduplicate items, strip mock strings, limit to 6."""
    seen = set()
    cleaned = []
    for item in items or []:
        if not item:
            continue
        val = _sanitize_text(item)
        if not val:
            continue
        if val.lower() not in seen:
            seen.add(val.lower())
            cleaned.append(val)
            if len(cleaned) == max_items:
                break
    return cleaned

def join_capabilities(capabilities: list[str]) -> str:
    """Join capabilities in natural language."""
    caps = clean_list(capabilities)
    if not caps:
        return ""
    if len(caps) == 1:
        return caps[0]
    if len(caps) == 2:
        return f"{caps[0]} and {caps[1]}"
    return ", ".join(caps[:-1]) + f", and {caps[-1]}"

def summarize_stack(frameworks: list, databases: list, languages: list = None) -> str:
    """Safely extract string names and group conceptually."""
    frameworks = frameworks or []
    databases = databases or []
    languages = languages or []
    f_names = clean_list([getattr(f, "name", str(f)) if not isinstance(f, str) else f for f in frameworks])
    d_names = clean_list([getattr(d, "name", str(d)) if not isinstance(d, str) else d for d in databases])
    l_names = clean_list([getattr(lang, "name", str(lang)) if not isinstance(lang, str) else lang for lang in languages])
    
    parts = []
    if l_names:
        parts.extend(l_names)
    if f_names:
        parts.extend(f_names)
    if d_names:
        parts.extend(d_names)
        
    if not parts:
        return ""
        
    return join_capabilities(parts)

def safe_product_summary(project_name: str, domain: str, capabilities: list[str], stack: str, confidence: str) -> str:
    """Assemble core overview sentences based on domain."""
    name = project_name or "This project"
    domain = {
        "repository_intelligence": "repository intelligence platform",
        "ai_hallucination_detection": "ai hallucination detection",
        "healthcare": "medical/healthcare assistance",
        "ecommerce": "e-commerce",
        "lms": "lms/education",
        "finance": "finance/accounting",
        "crm": "crm/business dashboard",
        "cms": "content/cms",
        "chatbot": "chatbot/assistant",
        "analytics": "data/analytics",
        "devops": "devops/automation",
        "generic_fullstack": "generic fullstack",
        "generic_backend": "generic backend",
    }.get(domain, domain)
    capabilities = capabilities or []
    caps = join_capabilities(capabilities)
    caps_lower = [str(cap).lower() for cap in capabilities if cap]
    stack_lower = (stack or "").lower()
    has_fastapi = "fastapi" in stack_lower
    has_diagnosis = any("diagnos" in cap for cap in caps_lower)
    has_retrieval = any(
        token in cap
        for cap in caps_lower
        for token in ["retriev", "knowledge", "rag", "search"]
    )
    has_offline = any("offline" in cap or "local ai inference" in cap for cap in caps_lower)
    strong_medical_backend = domain == "medical/healthcare assistance" and has_diagnosis and has_retrieval and has_fastapi

    # 1. Start with domain and purpose
    if domain == "repository intelligence platform" and confidence == "high":
        sent = f"{name} is a repository intelligence application focused on codebase analysis, question answering, and documentation workflows."
    elif domain == "repository intelligence platform":
        sent = f"{name} is a repository intelligence application that coordinates codebase analysis, question answering, and documentation workflows."
    elif domain == "ai hallucination detection":
        prefix = "is" if confidence == "high" else "is organized as"
        sent = f"{name} {prefix} an AI hallucination detection and fact-checking backend that evaluates claims or AI-generated answers using web-sourced evidence."
    elif domain == "medical/healthcare assistance":
        if strong_medical_backend:
            sent = f"{name} is an offline-first AI-assisted medical diagnosis and knowledge retrieval backend built with FastAPI."
            parts = [sent, "It exposes diagnosis and search APIs to support medical query workflows."]
            return clean_sentence(" ".join(_append_low_confidence(parts, confidence)))
        sent = f"{name} is an AI-assisted healthcare backend that supports diagnosis workflows and medical knowledge retrieval."
    elif domain == "e-commerce":
        sent = f"{name} is an e-commerce platform that supports product browsing, cart/order workflows, payments, and inventory/customer management."
    elif domain == "lms/education":
        sent = f"{name} is an education platform that supports course delivery, learning workflows, assessments, and student/teacher interactions."
    elif domain == "finance/accounting":
        sent = f"{name} is a finance-oriented application that supports transaction, billing, expense, or accounting workflows."
    elif domain == "crm/business dashboard":
        sent = f"{name} is a business dashboard or CRM-style application that supports customer, reporting, and operational workflows."
    elif domain == "content/cms":
        sent = f"{name} is a content management application that supports publishing, editing, and organizing content."
    elif domain == "chatbot/assistant":
        sent = f"{name} is an AI assistant or chatbot application that supports conversational querying and context-aware responses."
    elif domain == "data/analytics":
        sent = f"{name} is a data or analytics platform that supports data processing, reporting, and insight generation."
    elif domain == "devops/automation":
        sent = f"{name} is a DevOps or automation tool that supports workflow execution, deployment, or background processing."
    elif domain == "generic fullstack":
        stack_str = f" built with {stack}" if stack else ""
        parts = [f"{name} is organized as a fullstack application{stack_str}."]
        if caps:
            parts.append(f"It coordinates {caps} across the interface, application logic, and supporting data flow.")
        else:
            parts.append("It coordinates the repository's main workflow across the interface, application logic, and supporting data flow.")
        return clean_sentence(" ".join(_append_low_confidence(parts, confidence)))
    else: # generic backend
        stack_str = f" built with {stack}" if stack else ""
        parts = [f"{name} is organized as a backend API service{stack_str}."]
        if caps:
            parts.append(f"It concentrates {caps} within a maintainable service layer.")
        else:
            parts.append("It concentrates the repository's main workflow within a maintainable service layer.")
        return clean_sentence(" ".join(_append_low_confidence(parts, confidence)))

    # 2. Append capabilities and stack if explicitly not generic
    parts = [sent]
    
    if stack and "built with" not in sent:
        parts.append(f"It is built with {stack}.")
        
    if caps and domain not in ["generic fullstack", "generic backend"]:
        # Only add specific capabilities if we didn't already exhaust them in the domain summary
        parts.append(f"The detected capabilities include {caps}.")

    return clean_sentence(" ".join(_append_low_confidence(parts, confidence)))

def safe_remaining_summary(remaining_items: list) -> str:
    """Synthesizes remaining work into a readable sentence."""
    titles = [getattr(i, "title", str(i)) if not isinstance(i, str) else i for i in remaining_items]
    titles = clean_list(titles, max_items=5)
    if not titles:
        return "No significant missing components were detected."
    
    joined = join_capabilities([t.lower() for t in titles])
    return clean_sentence(f"Remaining work includes {joined}.")

def safe_risk_summary(risks: list) -> str:
    """Condenses risks into a professional summary."""
    titles = [getattr(i, "title", str(i)) if not isinstance(i, str) else i for i in risks]
    titles = clean_list(titles)
    if not titles:
        return "No critical issues detected."
    
    joined = join_capabilities([t.lower() for t in titles])
    return clean_sentence(f"Detected issues include {joined}.")

def safe_next_steps(remaining: list, risks: list) -> list[str]:
    """Derives actionable next steps based on remaining and risks."""
    steps = []
    
    for r in remaining:
        title = getattr(r, "title", str(r)).lower()
        if "auth" in title:
            steps.append("Add authentication before supporting private or sensitive workflows.")
        elif "test" in title:
            steps.append("Add tests for core functionality to ensure stability.")
        elif "ci/cd" in title or "pipeline" in title:
            steps.append("Add CI/CD pipelines to validate and deploy automatically.")
        elif "deploy" in title or "docker" in title:
            steps.append("Add deployment configuration for repeatable production setup.")
        elif "workflow" in title or "readme" in title or "doc" in title:
            steps.append("Improve workflow documentation to cover all system components.")
        elif "database" in title or "storage" in title:
            steps.append("Implement persistent storage for stateful workflows.")
            
    for risk in risks:
        rec = getattr(risk, "recommendation", "")
        if rec and "MagicMock" not in str(rec):
            steps.append(str(rec))
            
    if not steps:
        steps.append("Proceed with testing and final production validation.")

    return clean_list(steps, max_items=6)
