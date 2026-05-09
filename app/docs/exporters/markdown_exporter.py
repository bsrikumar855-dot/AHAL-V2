from app.docs.models import PRDResult
from app.docs.utils.evidence_sanitizer import sanitize_text
from app.intelligence.consistency_validator import OutputConsistencyValidator
from app.intelligence.output_guard import CanonicalOutputGuard

class MarkdownExporter:
    def __init__(self):
        self.validator = OutputConsistencyValidator()

    def _assert_canonical_domain_safety(self, prd_result: PRDResult) -> None:
        canonical = getattr(prd_result, "canonical_intelligence", None)
        if canonical is None:
            return
        checked_values = [
            getattr(canonical, "product_summary", ""),
            getattr(canonical, "what", ""),
            getattr(canonical, "why", ""),
            getattr(getattr(getattr(prd_result, "project_brief", None), "what", None), "content", ""),
            getattr(getattr(prd_result, "overview", None), "content", ""),
        ]
        for value in checked_values:
            CanonicalOutputGuard.assert_no_forbidden_terms(str(value or ""), canonical)

    def export(self, prd_result: PRDResult) -> str:
        prd_result = self.validator.validate_export_prd(prd_result)
        canonical = getattr(prd_result, "canonical_intelligence", None)
        self._assert_canonical_domain_safety(prd_result)
        lines = []
        repo_type = str(getattr(getattr(prd_result, "canonical_intelligence", None), "repo_type", "") or getattr(prd_result, "project_type", "") or "").lower()
        api_title = "Dataset Overview" if repo_type == "dataset" else "Package/API Surface" if repo_type in {"python_package", "npm_package", "component_library", "sdk"} else "API Surface"
        workflow_title = "Repository Structure" if repo_type in {"documentation", "curriculum", "knowledge_base"} else "Workflow"
        lines.append("# Project Requirement Document\n")
        
        # 1. Project Overview
        if canonical:
            lines.append(f"## 1. Project Overview\n\n{sanitize_text(CanonicalOutputGuard.sanitize_text(canonical.product_summary, canonical))}\n")
        else:
            lines.append(self._format_section("1. Project Overview", prd_result.overview))
        
        # 1.5 Project Intelligence Brief
        if getattr(prd_result, "project_brief", None):
            pb = prd_result.project_brief
            lines.append("## Project Intelligence Brief\n")
            lines.append(f"### Project Goal\n{sanitize_text(CanonicalOutputGuard.sanitize_text(getattr(canonical, 'project_goal', pb.goal.content), canonical))}\n")
            lines.append(f"### What This Project Is\n{sanitize_text(CanonicalOutputGuard.sanitize_text(getattr(canonical, 'what', pb.what.content), canonical))}\n")
            lines.append(f"### Why This Project Exists\n{sanitize_text(CanonicalOutputGuard.sanitize_text(getattr(canonical, 'why', pb.why.content), canonical))}\n")
            
            lines.append("### What Is Already Built\n")
            for item in (getattr(canonical, "completed", None) or pb.completed):
                lines.append(f"- **{item.title}**: {item.description}")
            lines.append("")
                
            lines.append("### What Is Remaining\n")
            for item in (getattr(canonical, "remaining", None) or pb.remaining):
                lines.append(f"- **{item.title}**: {item.description}")
            lines.append("")
            
            lines.append("### Current Issues\n")
            issues = getattr(canonical, "issues", None) or pb.issues
            if not issues:
                lines.append("No critical issues detected.\n")
            else:
                for issue in issues:
                    lines.append(f"- **{issue.title}** ({issue.severity}): {getattr(issue, 'description', issue.title)}")
            lines.append("")
                    
            lines.append("### Recommended Next Steps\n")
            for step in pb.next_steps:
                lines.append(f"- {step}")
            lines.append("")
        
        # 2. Architecture
        lines.append(self._format_section("2. Architecture", prd_result.architecture))
        
        # 3. Tech Stack
        lines.append(self._format_section("3. Tech Stack", prd_result.tech_stack))
        
        # 4. Core Modules
        lines.append("## 4. Core Modules\n")
        if not prd_result.modules:
            lines.append("Insufficient evidence from codebase.\n")
        else:
            lines.append("| Module | Category | Description | Files | Confidence |")
            lines.append("|---|---|---|---|---|")
            for mod in prd_result.modules:
                files_str = ", ".join(mod.files) if mod.files else "None"
                files_str = self._escape_table(files_str)
                name = self._escape_table(mod.name)
                cat = self._escape_table(mod.category)
                desc = self._escape_table(mod.description)
                conf = self._escape_table(mod.confidence)
                lines.append(f"| {name} | {cat} | {desc} | {files_str} | {conf} |")
            lines.append("")
            
        # 5. API Surface
        lines.append(f"## 5. {api_title}\n")
        if not prd_result.api_endpoints:
            if repo_type == "dataset":
                lines.append("Dataset content is described through repository files and metadata rather than HTTP endpoints.\n")
            elif repo_type in {"python_package", "npm_package", "component_library", "sdk"}:
                lines.append("No HTTP API endpoints were identified. This repository appears to expose package/library APIs instead.\n")
            else:
                lines.append("Insufficient evidence from codebase.\n")
        else:
            lines.append("| Method | Path | Framework | Source File | Confidence |")
            lines.append("|---|---|---|---|---|")
            for api in prd_result.api_endpoints:
                method = self._escape_table(api.method)
                path = self._escape_table(api.path)
                fw = self._escape_table(api.framework)
                src = self._escape_table(api.source_file or "Unknown")
                conf = self._escape_table(api.confidence)
                lines.append(f"| {method} | {path} | {fw} | {src} | {conf} |")
            lines.append("")
            
        # 6. Workflow
        lines.append(f"## 6. {workflow_title}\n")
        if not prd_result.workflow:
            lines.append("Insufficient evidence from codebase.\n")
        else:
            for wf in sorted(prd_result.workflow, key=lambda x: x.order):
                target = f" -> {wf.target}" if wf.target else ""
                lines.append(f"{wf.order}. **{wf.source}** {wf.action}{target} *(Confidence: {wf.confidence})*")
            lines.append("")
            
        # 7. Database / Storage
        lines.append(self._format_section("7. Database / Storage", prd_result.databases))
        
        # 8. Setup & Run Notes
        lines.append(self._format_section("8. Setup & Run Notes", prd_result.setup_notes))
        
        # 9. Risks & Gaps
        lines.append("## 9. Risks & Gaps\n")
        if not prd_result.risks:
            lines.append("No critical risks detected.\n")
        else:
            lines.append("| Title | Severity | Description | Recommendation |")
            lines.append("|---|---|---|---|")
            for risk in prd_result.risks:
                title = self._escape_table(risk.title)
                sev = self._escape_table(risk.severity)
                desc = self._escape_table(risk.description)
                rec = self._escape_table(risk.recommendation)
                lines.append(f"| {title} | {sev} | {desc} | {rec} |")
            lines.append("")
            
        # 10. Evidence Summary
        lines.append("## 10. Evidence Summary\n")
        lines.append(f"- **Overall Confidence**: {prd_result.confidence.title()}")
        lines.append(f"- **Total Evidence Items**: {prd_result.evidence_count}")
        if prd_result.warnings:
            lines.append("- **Warnings**:")
            for w in prd_result.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        
        markdown = "\n".join(lines)
        self._assert_canonical_domain_safety(prd_result)
        if canonical is not None:
            CanonicalOutputGuard.assert_no_forbidden_terms(markdown, canonical)
        return markdown

    def _format_section(self, title: str, section) -> str:
        lines = []
        lines.append(f"## {title}\n")
        
        if not section or not section.content:
            lines.append("Insufficient evidence from codebase.\n")
            return "\n".join(lines)
            
        lines.append(f"*(Confidence: {section.confidence.title()})*\n")
        
        if section.warnings:
            for w in section.warnings:
                lines.append(f"> **Warning**: {w}")
            lines.append("")
            
        lines.append(sanitize_text(section.content))
        lines.append("")
        return "\n".join(lines)
        
    def _escape_table(self, text: str) -> str:
        if not text:
            return ""
        return str(text).replace("|", "\\|").replace("\n", " ")
