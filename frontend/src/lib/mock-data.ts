import type {
  ApiResult,
  ChatResponse,
  IntelligenceData,
  OnboardingReport,
  PrdDiffResult,
  TestGapReport,
  TimelineItem,
} from "./types"
import { createId } from "./utils"

export const demoSessionId = "demo-ahal-session"
export const demoAccessToken = "demo-token-ahal"

export const demoIntelligence: IntelligenceData = {
  sessionId: demoSessionId,
  projectName: "AHAL AI Demo Workspace",
  projectType: "fullstack",
  repoVisibility: "Public",
  hallucinationRisk: "Low",
  architectureConfidence: "High",
  productPurposeConfidence: "High",
  projectGoal:
    "This demo workspace is designed to show how a repository intelligence product turns code analysis into clear, evidence-backed guidance. It combines chat, reporting, onboarding, and engineering insight workflows in a single frontend and backend experience.",
  projectSummary:
    "This demo workspace shows a repository intelligence product with analysis workflows, validated summaries, chat, reporting, and engineering insight generation across backend APIs and a premium frontend experience.",
  what:
    "The platform analyzes code artifacts, extracts technical structure, and turns the results into dashboards, reports, repo chat answers, onboarding material, and engineering deltas.",
  why:
    "It reduces ramp-up time for developers, makes project context easier to validate, and helps engineering teams move from raw code to actionable understanding.",
  remaining: [
    {
      title: "Live Connector Hardening",
      description: "Extend repository indexing and delta scan orchestration for larger multi-repo workspaces.",
    },
    {
      title: "Governed Exports",
      description: "Add organization-level export policies and review flows for downloadable reports.",
    },
  ],
  completed: [
    {
      title: "Repo Analysis Pipeline",
      description: "Supports code snippets, ZIP uploads, and GitHub repositories with timeline-driven analysis.",
    },
    {
      title: "Truth-Layer Reporting",
      description: "Generates evidence-backed project summaries, PRD exports, and safer domain-aware outputs.",
    },
  ],
  techStack: {
    languages: ["TypeScript", "Python", "CSS", "HTML"],
    frameworks: ["React", "Vite", "Tailwind CSS", "FastAPI"],
    databases: ["MongoDB", "SQLite"],
    tools: ["GitHub", "Pydantic"],
  },
  apiSurface: [
    { method: "POST", path: "/analyze/code", source: "app/api/analyze.py", purpose: "Creates a code analysis session." },
    { method: "POST", path: "/analyze/upload", source: "app/api/analyze.py", purpose: "Uploads a ZIP for repository analysis." },
    { method: "POST", path: "/analyze/github", source: "app/api/analyze.py", purpose: "Starts analysis for a GitHub repository." },
    { method: "POST", path: "/analyze/chat/{session_id}", source: "app/api/chat.py", purpose: "Answers project questions with evidence." },
  ],
  workflow: [
    { title: "Input Acquisition", description: "Code snippets, ZIP uploads, or repository URLs initiate an analysis session." },
    { title: "Fact Extraction", description: "Routes, modules, storage, risks, and workflow evidence are extracted into structured intelligence." },
    { title: "Validation Layer", description: "Truth-layer rules enforce conservative summaries, domain confidence, and evidence-backed claims." },
    { title: "Delivery", description: "Users explore dashboards, chat answers, onboarding reports, test gaps, and downloadable PRD artifacts." },
  ],
  evidence: [
    { label: "README.md", detail: "Project documentation describes repository analysis, chat, PRD generation, and report workflows." },
    { label: "app/api/chat.py", detail: "Detected analyze, chat, report, onboarding, and diff endpoints across the backend service." },
    { label: "frontend/src/pages/DashboardPage.tsx", detail: "Detected dashboard, chat, downloads, and reporting surfaces in the client application." },
  ],
  warnings: ["Demo data is being shown because no live backend session is attached."],
  issues: [
    {
      severity: "Medium",
      title: "Large repository indexing can take noticeable time before full report generation.",
      recommendation: "Expose richer async progress events and resumable indexing checkpoints.",
    },
  ],
  dataQuality: {
    normalized: false,
    notes: [],
  },
}

export const demoTimeline: TimelineItem[] = [
  {
    id: createId("timeline"),
    title: "Session created",
    status: "completed",
    timestamp: new Date().toISOString(),
    detail: "Analysis session initialized and ready for input ingestion.",
  },
  {
    id: createId("timeline"),
    title: "Evidence extracted",
    status: "completed",
    timestamp: new Date().toISOString(),
    detail: "Routes, frameworks, modules, and report signals were detected successfully.",
  },
  {
    id: createId("timeline"),
    title: "Project intelligence composed",
    status: "active",
    timestamp: new Date().toISOString(),
    detail: "Truth-layer validated summary, architecture, risks, and report outputs are available.",
  },
]

export const demoChatResponse: ChatResponse = {
  message: {
    id: createId("chat"),
    role: "assistant",
    content:
      "AHAL AI is a repository intelligence platform that analyzes source code, validates project purpose, and generates structured outputs such as chat answers, onboarding guides, PRD reports, and engineering deltas.",
    shortAnswer:
      "AHAL AI is a repository intelligence platform with analysis, chat, onboarding, and reporting workflows.",
    sections: [
      {
        title: "What It Does",
        content: "It turns repository evidence into structured project intelligence and downstream developer reports.",
        bullets: ["Analyzes code and repo inputs", "Generates chat, onboarding, and report outputs"],
        evidenceIds: ["E1", "E2"],
      },
    ],
    timestamp: new Date().toISOString(),
    confidence: "High",
    warnings: ["LLM polish unavailable — deterministic answer shown."],
    evidence: demoIntelligence.evidence,
    suggestedFollowups: ["What APIs exist?", "Explain the architecture.", "What tests should be added?"],
    intent: "project_overview",
    usedLlm: false,
    fallbackUsed: true,
  },
  suggestedQuestions: [
    "What APIs were detected in this project?",
    "Summarize the project workflow.",
    "What risks or gaps should the team address next?",
  ],
  demoMode: true,
}

export const demoTestGaps: TestGapReport = {
  summary: "Core analysis and export workflows exist, but integration coverage should be expanded for long-running jobs and report downloads.",
  items: [
    {
      area: "Analysis orchestration",
      gap: "Async indexing and progress updates need more end-to-end tests.",
      impact: "Large repository sessions may regress without early detection.",
    },
    {
      area: "Report downloads",
      gap: "PDF/Markdown/LaTeX export states need browser-level verification.",
      impact: "Users may hit download edge cases that unit tests do not catch.",
    },
  ],
}

export const demoOnboarding: OnboardingReport = {
  summary: "New contributors can get productive by understanding the analysis flow, truth layer, and export surfaces first.",
  steps: [
    {
      title: "Start at the analysis endpoints",
      detail: "Understand how code, ZIP, and GitHub sessions are created and tracked.",
    },
    {
      title: "Review truth-layer outputs",
      detail: "Read how product identity, evidence strength, and consistency rules shape user-facing summaries.",
    },
    {
      title: "Walk through dashboard surfaces",
      detail: "Inspect the intelligence, chat, download, and report-generation flows exposed to users.",
    },
  ],
}

export const demoDiff: PrdDiffResult = {
  summary: "The latest scan introduces richer report quality, more accurate product summaries, and improved frontend presentation.",
  changes: [
    { title: "Truth layer upgraded", detail: "Product-domain fallbacks are more conservative and evidence-backed." },
    { title: "Frontend v2", detail: "The client now includes an animated landing page, dashboard, chat, and download center." },
  ],
}

export function buildDemoSession(): ApiResult<{ sessionId: string; accessToken: string }> {
  return {
    data: { sessionId: demoSessionId, accessToken: demoAccessToken },
    demoMode: true,
  }
}

export function buildDemoDownload(format: "pdf" | "markdown" | "latex" | "json") {
  const commonTitle = `AHAL AI Demo Report (${format.toUpperCase()})`
  if (format === "json") {
    return {
      content: JSON.stringify(demoIntelligence, null, 2),
      filename: "ahal-demo-report.json",
      mimeType: "application/json",
      demoMode: true,
    }
  }

  if (format === "markdown") {
    return {
      content: `# ${commonTitle}\n\n## Executive Summary\n${demoIntelligence.projectSummary}\n`,
      filename: "ahal-demo-report.md",
      mimeType: "text/markdown",
      demoMode: true,
    }
  }

  if (format === "latex") {
    return {
      content: `\\section*{${commonTitle}}\n${demoIntelligence.projectSummary}`,
      filename: "ahal-demo-report.tex",
      mimeType: "application/x-tex",
      demoMode: true,
    }
  }

  return {
    content: `${commonTitle}\n\n${demoIntelligence.projectSummary}`,
    filename: "ahal-demo-report.pdf.txt",
    mimeType: "text/plain",
    demoMode: true,
  }
}
