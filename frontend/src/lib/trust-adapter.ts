import {
  dedupeParagraphText,
  dedupeSections,
  dedupeStrings,
  humanizeApiPurpose,
  normalizeApiPath,
  normalizeConfidence,
  safeText,
  sanitizeMarkupNoise,
  sanitizeChatMessage,
  sanitizeEvidenceDetail,
  sanitizeEvidenceLabel,
  sanitizePath,
} from "./presentation"
import type {
  ApiSurfaceItem,
  BackendChatResponse,
  BriefItem,
  ChatAnswerSection,
  IntelligenceResponse,
  NormalizedChatResponse,
  NormalizedIntelligence,
  ProjectType,
  TimelineEvent,
  TimelineItem,
  TimelineResponse,
  WorkflowStep,
} from "./types"
import { createId, titleCase, truncateMiddle } from "./utils"

const developerSignals = [
  "developer tool",
  "code changes",
  "structured knowledge",
  "queryable knowledge",
  "code intelligence",
  "repository",
  "repo",
  "codebase",
  "project intelligence",
]

const databaseSignals = ["mongodb", "sqlite", "postgresql", "postgres", "mysql", "redis"]
const frameworkSignals = ["fastapi", "react", "next.js", "next", "vite", "tailwind", "tailwindcss", "flask", "express"]
const toolSignals = ["docker", "github actions", "celery", "pytest", "eslint", "pnpm", "npm"]
const languageExtensions: Array<[RegExp, string]> = [
  [/\.(py)$/i, "Python"],
  [/\.(tsx?|mts|cts)$/i, "TypeScript"],
  [/\.(jsx?|mjs|cjs)$/i, "JavaScript"],
  [/\.(css)$/i, "CSS"],
  [/\.(html)$/i, "HTML"],
]
const starterQuestions = [
  "What does this project do?",
  "What is built?",
  "What remains?",
  "What APIs exist?",
  "What are the risks?",
  "What should a new engineer read first?",
  "Explain the architecture.",
  "What tests should be added?",
  "How does the main workflow work?",
  "How do I run this project?",
]

function toArray(value: unknown) {
  return Array.isArray(value) ? value : []
}

function toText(value: unknown, fallback = "") {
  return safeText(value, fallback)
}

function displayText(value: unknown, fallback = "") {
  return sanitizeMarkupNoise(safeText(value, ""), fallback)
}

function applyCanonicalDeveloperGuard(text: string, canonical?: IntelligenceResponse["canonical_intelligence"]): string {
  const value = toText(text)
  if (!canonical) {
    return value
  }
  const canonicalSummary = toText(canonical.product_summary)
  const canonicalWhat = toText(canonical.what)
  const joined = `${canonicalSummary} ${canonicalWhat}`.toLowerCase()
  const isDeveloperIdentity = joined.includes("code intelligence") || joined.includes("developer tool")
  if (!isDeveloperIdentity) {
    return value
  }
  if (
    /content management application|financial research|finance workflows|Backend API Layer|unfamiliar codebases|repository-aware questions|\.env\.example|mongodb:\/\//i.test(value)
  ) {
    return canonicalWhat || canonicalSummary || value
  }
  return value
}

function normalizeProjectType(value: unknown): ProjectType {
  const normalized = toText(value).toLowerCase()
  const directMatches: ProjectType[] = [
    "documentation",
    "curriculum",
    "knowledge_base",
    "mobile_app",
    "cli_tool",
    "python_package",
    "npm_package",
    "component_library",
    "sdk",
    "plugin",
    "browser_extension",
    "vscode_extension",
    "ml_model_repo",
    "data_science_notebooks",
    "dataset",
    "template",
    "infrastructure",
    "devops_automation",
    "design_assets",
    "research_code",
    "monorepo",
    "mixed",
  ]
  if (directMatches.includes(normalized as ProjectType)) {
    return normalized as ProjectType
  }
  if (normalized.includes("curriculum")) {
    return "curriculum"
  }
  if (normalized.includes("documentation")) {
    return "documentation"
  }
  if (normalized.includes("knowledge")) {
    return "knowledge_base"
  }
  if (normalized.includes("front")) {
    return "frontend"
  }
  if (normalized.includes("back")) {
    return "backend"
  }
  if (normalized.includes("full")) {
    return "fullstack"
  }
  return "unknown"
}

function getExplicitDescription(raw: IntelligenceResponse): string {
  const candidates = [
    raw.project_goal,
    raw.summary?.what,
    raw.summary?.why,
    ...toArray(raw.core_features),
    ...toArray(raw.evidence).flatMap((item) => {
      if (!item || typeof item !== "object") {
        return []
      }
      const record = item as Record<string, unknown>
      return [record.label, record.title, record.detail, record.reason, record.snippet]
    }),
  ]

  for (const candidate of candidates) {
    const text = displayText(candidate)
    if (!text) {
      continue
    }

    if (/explicit product description says:/i.test(text)) {
      return text.replace(/.*explicit product description says:\s*/i, "").trim()
    }

    if (developerSignals.some((signal) => text.toLowerCase().includes(signal))) {
      return text
    }
  }

  return ""
}

function normalizeProductSummary(raw: IntelligenceResponse, explicitDescription: string): string {
  const canonical = raw.canonical_intelligence
  if (canonical?.product_summary) {
    return dedupeParagraphText(applyCanonicalDeveloperGuard(displayText(canonical.product_summary, "Project purpose is not fully specified in the analyzed evidence."), canonical))
  }
  const lower = explicitDescription.toLowerCase()
  if (
    explicitDescription &&
    lower.includes("ai-powered developer tool") &&
    lower.includes("structured") &&
    lower.includes("queryable knowledge")
  ) {
    return "ContextBridge AI appears to be an AI-powered developer tool that transforms code changes into structured, queryable knowledge. It includes a Next.js/React frontend, FastAPI backend, MongoDB/SQLite storage evidence, chat/query workflows, session tracking, and analysis APIs."
  }

  if (explicitDescription) {
    const normalized = explicitDescription.replace(/\.$/, "")
    return `${displayText(raw.project_name, "This project")} appears to be ${normalized}.`
  }

  const fallback = displayText(raw.summary?.what ?? raw.project_goal, "Project intelligence is available for this session.")
  if (/content management application/i.test(fallback) && !/cms|content management/i.test(explicitDescription)) {
    return "This project appears to be a developer intelligence platform based on the available code and metadata."
  }

  return fallback
}

function normalizeProjectGoal(raw: IntelligenceResponse, explicitDescription: string): string {
  const canonical = raw.canonical_intelligence
  if (canonical?.project_goal) {
    return applyCanonicalDeveloperGuard(displayText(canonical.project_goal, "Project goal is not fully specified in the analyzed evidence."), canonical)
  }
  if (raw.project_goal) {
    return displayText(raw.project_goal, "Project goal is not fully specified in the analyzed evidence.")
  }
  const fallback = displayText(raw.summary?.what ?? raw.project_goal, "Project goal is not fully specified in the analyzed evidence.")
  if (explicitDescription && fallback === explicitDescription) {
    return applyCanonicalDeveloperGuard(fallback, canonical)
  }
  return fallback
}

function normalizeRepoVisibility(raw: IntelligenceResponse): "Public" | "Private" | "Unknown" {
  const canonical = toText(raw.canonical_intelligence?.repo_visibility ?? raw.repo_visibility)
    .trim()
    .toLowerCase()

  if (canonical.includes("public")) {
    return "Public"
  }
  if (canonical.includes("private")) {
    return "Private"
  }
  return "Unknown"
}

function normalizeHallucinationRisk(raw: IntelligenceResponse): "High" | "Medium" | "Low" | "Unknown" {
  const canonical = toText(raw.canonical_intelligence?.hallucination_risk ?? raw.hallucination_risk)
    .trim()
    .toLowerCase()

  if (canonical.includes("high")) {
    return "High"
  }
  if (canonical.includes("medium")) {
    return "Medium"
  }
  if (canonical.includes("low")) {
    return "Low"
  }
  return "Unknown"
}

function normalizeWhat(raw: IntelligenceResponse, explicitDescription: string): string {
  const canonical = raw.canonical_intelligence
  if (canonical?.what) {
    return applyCanonicalDeveloperGuard(displayText(canonical.what, "The exact product behavior is only partially described by the available intelligence output."), canonical)
  }
  if (explicitDescription) {
    return explicitDescription
  }

  const fallback = displayText(raw.summary?.what, "The exact product behavior is only partially described by the available intelligence output.")
  if (/content management application/i.test(fallback)) {
    return applyCanonicalDeveloperGuard("This project appears to be a developer intelligence platform based on the available code and metadata.", canonical)
  }
  return fallback
}

function normalizeWhy(raw: IntelligenceResponse): string {
  const canonical = raw.canonical_intelligence
  if (canonical?.why) {
    return applyCanonicalDeveloperGuard(displayText(canonical.why, "The business or user-facing reason is not fully specified in the analyzed evidence."), canonical)
  }
  return displayText(raw.summary?.why, "The business or user-facing reason is not fully specified in the analyzed evidence.")
}

function collectEvidenceStrings(raw: IntelligenceResponse): string[] {
  return toArray(raw.evidence).flatMap((item) => {
    if (!item || typeof item !== "object") {
      return []
    }
    const record = item as Record<string, unknown>
    return [record.path, record.file, record.label, record.source, record.source_id].map((entry) => toText(entry)).filter(Boolean)
  })
}

function normalizeTechStack(raw: IntelligenceResponse): NormalizedIntelligence["techStack"] {
  const canonical = raw.canonical_intelligence
  if (canonical?.tech_stack) {
    return {
      languages: dedupeStrings(toArray(canonical.tech_stack.languages).map((item) => toText(item)).filter(Boolean)),
      frameworks: dedupeStrings(toArray(canonical.tech_stack.frameworks).map((item) => toText(item)).filter(Boolean)),
      databases: dedupeStrings(toArray(canonical.tech_stack.databases).map((item) => toText(item)).filter(Boolean)),
      tools: dedupeStrings(toArray(canonical.tech_stack.tools).map((item) => toText(item)).filter(Boolean)),
    }
  }
  const techStack = {
    languages: [] as string[],
    frameworks: [] as string[],
    databases: [] as string[],
    tools: [] as string[],
  }

  const add = (group: keyof typeof techStack, value: string) => {
    const label = toText(value)
    if (!label) {
      return
    }
    if (!techStack[group].some((item) => item.toLowerCase() === label.toLowerCase())) {
      techStack[group].push(label)
    }
  }

  const rawItems = [
    ...toArray(raw.technical?.tech_stack).flatMap((item) => {
      if (typeof item === "string") {
        return [item]
      }
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>
        return [record.category, ...toArray(record.items)]
      }
      return []
    }),
    ...toArray(raw.technical?.database),
    ...collectEvidenceStrings(raw),
  ]

  for (const item of rawItems) {
    const text = toText(item)
    if (!text) {
      continue
    }

    const lower = text.toLowerCase()
    if (databaseSignals.some((signal) => lower.includes(signal))) {
      add("databases", titleCase(lower.replace(/^storage:\s*/i, "")))
      continue
    }
    if (frameworkSignals.some((signal) => lower.includes(signal))) {
      const normalized = lower === "next" ? "Next.js" : lower === "tailwindcss" ? "Tailwind" : titleCase(text)
      add("frameworks", normalized)
      continue
    }
    if (toolSignals.some((signal) => lower.includes(signal))) {
      add("tools", titleCase(text))
      continue
    }
  }

  for (const evidence of collectEvidenceStrings(raw)) {
    for (const [pattern, language] of languageExtensions) {
      if (pattern.test(evidence)) {
        add("languages", language)
      }
    }
    if (/\.(md|mdx|rst)$/i.test(evidence)) {
      add("languages", "Markdown")
    }
  }

  return {
    languages: dedupeStrings(techStack.languages),
    frameworks: dedupeStrings(techStack.frameworks),
    databases: dedupeStrings(techStack.databases),
    tools: dedupeStrings(techStack.tools),
  }
}

function apiPriority(path: string): number {
  if (path === "/health" || path === "/" || path.startsWith("/status")) {
    return 0
  }
  if (path.includes("/analyze")) {
    return 1
  }
  if (path.includes("/query") || path.includes("/chat") || path.includes("/ask") || path.includes("/context")) {
    return 2
  }
  if (path.includes("/history") || path.includes("/session") || path.includes("/stream")) {
    return 3
  }
  if (path.includes("/report") || path.includes("/summary") || path.includes("/summarize") || path.includes("/intelligence")) {
    return 4
  }
  return 5
}

function normalizeApiSurface(raw: IntelligenceResponse): ApiSurfaceItem[] {
  const canonical = raw.canonical_intelligence
  if (canonical?.api_surface?.length) {
    return toArray(canonical.api_surface).map((item) => {
      const record = item as Record<string, unknown>
      return {
        method: toText(record.method, "GET").toUpperCase(),
        path: normalizeApiPath(toText(record.path, "/")),
        purpose: toText(record.purpose, humanizeApiPurpose(toText(record.method, "GET"), toText(record.path, "/"))),
        source: sanitizePath(toText(record.source, "Detected API surface")) || "Detected API surface",
      }
    })
  }
  const items = new Map<string, ApiSurfaceItem>()

  for (const item of toArray(raw.technical?.api_surface)) {
    if (!item || typeof item !== "object") {
      continue
    }

    const record = item as Record<string, unknown>
    const method = toText(record.method, "GET").toUpperCase()
    const path = normalizeApiPath(toText(record.path, "/"))
    const key = `${method} ${path}`
    if (items.has(key)) {
      continue
    }

    items.set(key, {
      method,
      path,
      purpose: humanizeApiPurpose(method, path),
      source: sanitizePath(toText(record.source ?? record.framework, "Detected API surface")) || "Detected API surface",
    })
  }

  return Array.from(items.values()).sort((left, right) => {
    const priority = apiPriority(left.path) - apiPriority(right.path)
    if (priority !== 0) {
      return priority
    }
    return `${left.method} ${left.path}`.localeCompare(`${right.method} ${right.path}`)
  })
}

function pushCompleted(result: BriefItem[], seen: Set<string>, title: string, description: string) {
  const key = title.toLowerCase()
  if (seen.has(key)) {
    return
  }
  seen.add(key)
  result.push({ title, description })
}

function normalizeCompleted(raw: IntelligenceResponse, apiSurface: ApiSurfaceItem[], techStack: NormalizedIntelligence["techStack"]): BriefItem[] {
  const canonical = raw.canonical_intelligence
  if (canonical?.completed?.length) {
    return toArray(canonical.completed).map((item) => {
      const record = item as Record<string, unknown>
      return {
        title: toText(record.title, "Detected capability"),
        description: toText(record.description, "Capability details were not returned."),
      }
    })
  }
  const result: BriefItem[] = []
  const seen = new Set<string>()
  const repoType = toText(canonical?.repo_type).toLowerCase()

  if (repoType === "curriculum" || repoType === "documentation" || repoType === "knowledge_base") {
    pushCompleted(result, seen, repoType === "curriculum" ? "Study Plan Documentation" : "Documentation Content", "README-based documentation is present and describes the repository content.")
    pushCompleted(result, seen, repoType === "curriculum" ? "Learning Roadmap" : "Resource Organization", "Structured sections organize topics, resources, and learning progression for readers.")
    if (repoType === "curriculum") {
      pushCompleted(result, seen, "Interview Preparation Content", "Interview preparation topics and supporting resources were detected in the documentation.")
    }
    return result
  }
  if (repoType === "cli_tool") {
    pushCompleted(result, seen, "Command Interface", "A command-line entry point or executable interface was detected.")
    pushCompleted(result, seen, "Argument Parsing", "Command arguments, flags, or subcommands are configured for the CLI surface.")
    pushCompleted(result, seen, "Execution Logic", "The repository includes command execution logic for the requested workflow.")
    pushCompleted(result, seen, "Packaging Metadata", "Packaging or distribution metadata was detected for the CLI tool.")
    return result
  }
  if (["python_package", "npm_package", "component_library", "sdk"].includes(repoType)) {
    pushCompleted(result, seen, "Public API Surface", "Exported package or library APIs were detected for downstream consumers.")
    pushCompleted(result, seen, "Package Metadata", "Package distribution metadata was detected in repository manifests.")
    pushCompleted(result, seen, "Examples / Documentation", "Documentation or usage examples were detected for package consumers.")
    return result
  }
  if (repoType === "dataset") {
    pushCompleted(result, seen, "Dataset Files", "Dataset assets were detected in the repository.")
    pushCompleted(result, seen, "Metadata / Schema Documentation", "Supporting metadata or schema documentation was detected.")
    pushCompleted(result, seen, "Licensing Information", "Dataset licensing or reuse guidance was detected where available.")
    return result
  }

  if (techStack.frameworks.some((item) => /react|vite|next/i.test(item))) {
    pushCompleted(result, seen, "Frontend Application", "A frontend application is present for dashboard, chat, analysis, or report workflows.")
  }
  if (techStack.frameworks.some((item) => /fastapi|flask|express/i.test(item))) {
    pushCompleted(result, seen, "Backend API Surface", "A backend API surface is present to process project analysis and response workflows.")
  }
  if (apiSurface.some((item) => /\/ask|\/chat|\/query/.test(item.path))) {
    pushCompleted(result, seen, "Chat / Query API", "Grounded chat or query endpoints were detected.")
  }
  if (apiSurface.some((item) => item.path.includes("/analyze"))) {
    pushCompleted(result, seen, "Analysis API", "Analysis endpoints were detected for session creation or repository processing.")
  }
  if (apiSurface.some((item) => item.path.includes("/context"))) {
    pushCompleted(result, seen, "Context Retrieval API", "Context build or retrieval endpoints were detected.")
  }
  if (apiSurface.some((item) => item.path.includes("/history"))) {
    pushCompleted(result, seen, "Session History API", "Session history retrieval endpoints were detected.")
  }
  if (apiSurface.some((item) => item.path.includes("/stream"))) {
    pushCompleted(result, seen, "Streaming Updates", "Streaming session updates were detected in the API surface.")
  }
  if (apiSurface.some((item) => item.path.includes("/report") || item.path.includes("/summary") || item.path.includes("/summarize"))) {
    pushCompleted(result, seen, "Report / Summary API", "Report or summary generation endpoints were detected.")
  }
  if (techStack.databases.length) {
    pushCompleted(result, seen, "Storage Integration", `Storage evidence includes ${techStack.databases.join(", ")}.`)
  }
  if (apiSurface.some((item) => item.path === "/" || item.path === "/health" || item.path.startsWith("/status"))) {
    pushCompleted(result, seen, "Health / Status Endpoints", "Health, root, or status endpoints were detected for service readiness and progress tracking.")
  }
  if (collectEvidenceStrings(raw).some((item) => /dockerfile|package\.json|requirements\.txt|eslint|pytest/i.test(item))) {
    pushCompleted(result, seen, "Setup Configuration", "Setup and configuration artifacts were detected in the analyzed project.")
  }

  if (!result.length) {
    pushCompleted(result, seen, "Backend API Surface", "Structured backend capabilities were detected, but the returned intelligence was limited.")
  }

  return result
}

function normalizeRemaining(raw: IntelligenceResponse): BriefItem[] {
  const canonical = raw.canonical_intelligence
  if (canonical?.remaining?.length) {
    return toArray(canonical.remaining).map((item) => {
      const record = item as Record<string, unknown>
      return {
        title: toText(record.title, "Remaining work"),
        description: toText(record.description ?? record.title, "Remaining work"),
      }
    })
  }
  const seen = new Set<string>()
  const result: BriefItem[] = []

  for (const item of toArray(raw.summary?.remaining)) {
    const text = typeof item === "string"
      ? item
      : toText((item as Record<string, unknown>).title ?? (item as Record<string, unknown>).description)
    const normalized = toText(text)
    if (!normalized) {
      continue
    }

    const label = /no ci\/cd detected/i.test(normalized) || /ci\/cd pipeline not detected/i.test(normalized)
      ? "CI/CD pipeline not detected."
      : normalized
    const key = label.toLowerCase()
    if (seen.has(key)) {
      continue
    }
    seen.add(key)
    result.push({ title: label, description: label })
  }

  return result
}

function normalizeIssues(raw: IntelligenceResponse): NormalizedIntelligence["issues"] {
  const canonical = raw.canonical_intelligence
  if (canonical?.issues?.length) {
    return toArray(canonical.issues).map((item) => {
      const record = item as Record<string, unknown>
      return {
        severity: normalizeConfidence(record.severity),
        title: toText(record.title, "Detected issue"),
        recommendation: toText(record.recommendation, "Review this returned issue and confirm whether follow-up action is needed."),
      }
    })
  }
  const result: NormalizedIntelligence["issues"] = []
  const seen = new Set<string>()

  for (const item of toArray(raw.risks)) {
    const title =
      typeof item === "string"
        ? toText(item)
        : toText((item as Record<string, unknown>).title ?? (item as Record<string, unknown>).issue)
    if (!title) {
      continue
    }

    const key = title.toLowerCase()
    if (seen.has(key)) {
      continue
    }
    seen.add(key)
    result.push({
      severity: typeof item === "string" ? "Medium" : normalizeConfidence((item as Record<string, unknown>).severity),
      title,
      recommendation:
        typeof item === "string"
          ? "Review this returned issue and confirm whether follow-up action is needed."
          : toText((item as Record<string, unknown>).recommendation, "Review this returned issue and confirm whether follow-up action is needed."),
    })
  }

  if (!result.length) {
    return [
      {
        severity: "Neutral",
        title: "No critical issues were returned for this session.",
        recommendation: "No immediate remediation guidance was returned.",
      },
    ]
  }

  return result
}

function normalizeWorkflow(raw: IntelligenceResponse, projectType: ProjectType): WorkflowStep[] {
  const canonical = raw.canonical_intelligence
  const repoType = toText(canonical?.repo_type).toLowerCase()
  if (canonical?.workflow?.length) {
    return toArray(canonical.workflow).map((item) => {
      const record = item as Record<string, unknown>
      return {
        title: toText(record.title, "Workflow step"),
        description: toText(record.description, "Workflow step returned by backend."),
      }
    })
  }
  const joined = JSON.stringify(toArray(raw.technical?.workflow)).toLowerCase()
  const impossible = joined.includes("types/index.ts") || (joined.includes("frontend") && joined.includes("fastapi") && joined.includes("initializes"))
  if (projectType === "curriculum" || projectType === "documentation" || projectType === "knowledge_base") {
    return [
      { title: "Reader opens the repository documentation", description: "Reader opens the repository documentation." },
      { title: "README introduces the study plan or guide", description: "README introduces the study plan or guide." },
      { title: "Sections organize topics and progression", description: "Sections organize topics, resources, and learning progression." },
      { title: "Supporting docs expand accessibility", description: "Optional translations or supporting files expand accessibility." },
      { title: "Learner follows the roadmap", description: "Learner follows the roadmap independently." },
    ]
  }
  if (projectType === "cli_tool" || repoType === "cli_tool") {
    return [
      { title: "Run the CLI command", description: "A user executes the command-line interface with arguments or subcommands." },
      { title: "Parse flags and arguments", description: "The CLI parses user input and selects the requested command handler." },
      { title: "Execute command logic", description: "The tool performs the requested workflow." },
      { title: "Use configured files or services", description: "Optional files, configs, or supporting services are used when configured." },
      { title: "Return terminal output", description: "The CLI prints results, logs, or exit status for the user." },
    ]
  }
  if (["python_package", "npm_package", "component_library", "sdk"].includes(projectType) || ["python_package", "npm_package", "component_library", "sdk"].includes(repoType)) {
    return [
      { title: "Install the package", description: "A developer adds the package/library to another project." },
      { title: "Import public APIs", description: "The consuming application imports exported modules, functions, or components." },
      { title: "Execute package logic", description: "The library performs the requested functionality inside the host application." },
      { title: "Use optional integrations", description: "Configured dependencies or platform clients are used where required." },
      { title: "Return results to caller", description: "The package returns values, behavior, or UI output through its public API surface." },
    ]
  }
  if (projectType === "dataset" || repoType === "dataset") {
    return [
      { title: "Download dataset assets", description: "A downstream user accesses the dataset files." },
      { title: "Review metadata and schema", description: "Supporting documentation explains dataset structure and meaning." },
      { title: "Load files into tooling", description: "Consumers parse the files in their own analysis or training workflow." },
      { title: "Validate quality and provenance", description: "Consumers check schema, licensing, and quality as needed." },
      { title: "Use the dataset downstream", description: "The repository supports analysis, reporting, or model training elsewhere." },
    ]
  }

  if (projectType === "backend") {
    return [
      { title: "Receive client request", description: "Client/API consumer sends a request." },
      { title: "Validate in route handler", description: "FastAPI route handler receives and validates the request." },
      { title: "Run service logic", description: "Application or service logic performs the requested work." },
      { title: "Use storage if needed", description: "Storage is used when required by the backend workflow." },
      { title: "Return structured response", description: "A structured response is returned to the client." },
    ]
  }

  if (projectType === "frontend") {
    return [
      { title: "Open frontend application", description: "User opens the frontend application." },
      { title: "Render pages and components", description: "React/Vite/Next.js renders pages and components." },
      { title: "Call configured API service", description: "UI components call an API service when one is configured." },
      { title: "Handle external response", description: "External backend or API handles requests if detected." },
    ]
  }

  if (impossible || !toArray(raw.technical?.workflow).length) {
    return [
      { title: "Open frontend application", description: "User opens frontend application." },
      { title: "Render dashboard and input flows", description: "Next.js/React frontend renders dashboard and input workflows." },
      { title: "Call backend APIs", description: "Frontend calls backend API endpoints." },
      { title: "Process requests in FastAPI", description: "FastAPI route handlers process analysis, chat, context, status, or report requests." },
      { title: "Use services and storage", description: "Service layer uses storage/configuration when required." },
      { title: "Return structured intelligence", description: "Backend returns structured project intelligence to the frontend." },
    ]
  }

  return [
    { title: "Open frontend application", description: "User opens frontend application." },
    { title: "Render dashboard and input flows", description: "Next.js/React frontend renders dashboard and input workflows." },
    { title: "Call backend APIs", description: "Frontend calls backend API endpoints." },
    { title: "Process requests in FastAPI", description: "FastAPI route handlers process analysis, chat, context, status, or report requests." },
    { title: "Use services and storage", description: "Service layer uses storage/configuration when required." },
    { title: "Return structured intelligence", description: "Backend returns structured project intelligence to the frontend." },
  ]
}

function preferredEvidenceOrder(label: string): number {
  const preferred = ["readme.md", "requirements.txt", "package.json", "app/main.py", "api/v1/chat.py", "api/v1/code.py", "api/v1/repo.py", "db/mongodb.py", "dockerfile"]
  const lower = label.toLowerCase()
  const index = preferred.findIndex((item) => lower.includes(item))
  return index === -1 ? preferred.length : index
}

function normalizeEvidence(raw: IntelligenceResponse): NormalizedIntelligence["evidence"] {
  const canonical = raw.canonical_intelligence
  if (canonical?.evidence?.length) {
    return toArray(canonical.evidence).map((item) => {
      const record = item as Record<string, unknown>
      return {
        label: sanitizePath(toText(record.label)) || toText(record.label),
        detail: sanitizeEvidenceDetail(record.reason),
      }
    }).filter((item) => item.label)
  }
  const result: NormalizedIntelligence["evidence"] = []
  const seen = new Set<string>()

  for (const item of toArray(raw.evidence)) {
    const label = sanitizeEvidenceLabel(item)
    if (!label) {
      continue
    }

    const key = label.toLowerCase()
    if (seen.has(key)) {
      continue
    }
    seen.add(key)

    const record = item as Record<string, unknown>
    const detail = sanitizeEvidenceDetail(record.detail ?? record.reason ?? record.snippet ?? "")
    result.push({
      label,
      detail: detail || undefined,
    })
  }

  return result.sort((left, right) => preferredEvidenceOrder(left.label) - preferredEvidenceOrder(right.label)).slice(0, 8)
}

function normalizeWarnings(rawWarnings: unknown): string[] {
  return dedupeStrings(
    toArray(rawWarnings)
      .filter((item): item is string => typeof item === "string")
      .map((item) => {
        const lower = item.toLowerCase()
        if (
          lower.includes("llm")
          && (
            lower.includes("unavailable")
            || lower.includes("disabled")
            || lower.includes("api key missing")
            || lower.includes("api call failed")
            || lower.includes("execution failed")
          )
        ) {
          return "LLM polish unavailable — deterministic answer shown."
        }
        return toText(item)
      })
      .filter((item) => item && !/crm|cms|analytics|devops|chatbot|detected domain signals|unknown|normalized unsupported evidence/i.test(item)),
  )
}

function buildDataQuality(raw: IntelligenceResponse, normalized: Omit<NormalizedIntelligence, "dataQuality">) {
  const canonical = raw.canonical_intelligence
  if (canonical?.data_quality) {
    return {
      normalized: Boolean(canonical.data_quality.normalized),
      notes: dedupeStrings(toArray(canonical.data_quality.notes).map((item) => toText(item)).filter(Boolean)),
    }
  }
  const notes: string[] = []
  const rawApiCount = toArray(raw.technical?.api_surface).length
  const rawEvidenceCount = toArray(raw.evidence).length

  if (normalized.projectSummary !== toText(raw.summary?.what ?? raw.project_goal)) {
    notes.push("Summary wording was cleaned for product-facing presentation.")
  }
  if (normalized.apiSurface.length < rawApiCount) {
    notes.push("Duplicate API endpoints were removed.")
  }
  if (normalized.evidence.length < rawEvidenceCount) {
    notes.push("Evidence was deduplicated and sensitive labels were removed.")
  }
  if (!toText(raw.summary?.why)) {
    notes.push("Missing product-purpose rationale was rendered conservatively.")
  }
  if (normalized.remaining.some((item) => item.title === "CI/CD pipeline not detected.")) {
    notes.push("Repeated remaining-work items were grouped.")
  }

  return {
    normalized: notes.length > 0,
    notes,
  }
}

// TODO: Backend should eventually return normalized presentation fields directly.
export function normalizeIntelligence(raw: unknown): NormalizedIntelligence {
  const intelligence = (raw ?? {}) as IntelligenceResponse
  const explicitDescription = getExplicitDescription(intelligence)
  const projectType = normalizeProjectType(intelligence.canonical_intelligence?.project_type ?? intelligence.project_type ?? intelligence.architecture_style)
  const techStack = normalizeTechStack(intelligence)
  const apiSurface = normalizeApiSurface(intelligence)
  const normalizedBase: Omit<NormalizedIntelligence, "dataQuality"> = {
    sessionId: toText(intelligence.canonical_intelligence?.session_id ?? intelligence.session_id),
    projectName: displayText(intelligence.canonical_intelligence?.project_name ?? intelligence.project_name, "Analyzed Project"),
    projectGoal: normalizeProjectGoal(intelligence, explicitDescription),
    projectSummary: normalizeProductSummary(intelligence, explicitDescription),
    projectType,
    repoType: toText(intelligence.canonical_intelligence?.repo_type),
    repoVisibility: normalizeRepoVisibility(intelligence),
    hallucinationRisk: normalizeHallucinationRisk(intelligence),
    architectureConfidence: normalizeConfidence(intelligence.canonical_intelligence?.confidence?.architecture ?? intelligence.architecture_confidence ?? intelligence.confidence),
    productPurposeConfidence: normalizeConfidence(intelligence.canonical_intelligence?.confidence?.product_purpose ?? (explicitDescription ? "High" : intelligence.product_purpose_confidence ?? intelligence.confidence)),
    what: normalizeWhat(intelligence, explicitDescription),
    why: normalizeWhy(intelligence),
    completed: normalizeCompleted(intelligence, apiSurface, techStack),
    remaining: normalizeRemaining(intelligence),
    issues: normalizeIssues(intelligence),
    techStack,
    apiSurface,
    workflow: normalizeWorkflow(intelligence, projectType),
    evidence: normalizeEvidence(intelligence),
    warnings: normalizeWarnings(intelligence.warnings),
  }

  return {
    ...normalizedBase,
    dataQuality: buildDataQuality(intelligence, normalizedBase),
  }
}

export function normalizeChatResponse(raw: unknown): NormalizedChatResponse {
  const response = (raw ?? {}) as BackendChatResponse
  const evidence = normalizeEvidence({
    evidence: toArray(response.evidence) as Array<Record<string, unknown>>,
  })
  const sections: ChatAnswerSection[] = toArray(response.sections).map((item, index) => {
    const section = (item ?? {}) as Record<string, unknown>
    return {
      title: toText(section.title, `Section ${index + 1}`),
      content: toText(section.content),
      bullets: toArray(section.bullets).map((bullet) => toText(bullet)).filter(Boolean),
      evidenceIds: toArray(section.evidence_ids).map((evidenceId) => toText(evidenceId).replace(/^\[|\]$/g, "")).filter(Boolean),
    }
  }).filter((item) => item.title || item.content || item.bullets.length)

  const message = sanitizeChatMessage({
    id: createId("chat"),
    role: "assistant",
    content: dedupeParagraphText(toText(response.answer, "No answer was returned for this question.")),
    shortAnswer: dedupeParagraphText(toText(response.short_answer)),
    sections: dedupeSections(sections),
    timestamp: new Date().toISOString(),
    confidence: (normalizeConfidence(response.confidence) === "Unknown" ? "Low" : normalizeConfidence(response.confidence)) as "High" | "Medium" | "Low",
    warnings: normalizeWarnings(response.warnings),
    evidence,
    suggestedFollowups: dedupeStrings(toArray(response.suggested_followups).map((item) => toText(item)).filter(Boolean)),
    intent: toText(response.intent),
    usedLlm: Boolean(response.used_llm),
    fallbackUsed: response.fallback_used !== false,
  })

  return {
    message,
    suggestedQuestions: dedupeStrings([
      ...toArray(response.suggested_followups).map((item) => toText(item)).filter(Boolean),
      ...starterQuestions,
    ]),
  }
}

export function normalizeTimeline(raw: unknown): TimelineItem[] {
  const timeline = raw as TimelineResponse | TimelineEvent[]
  const events = Array.isArray(timeline) ? timeline : toArray(timeline?.events)
  const seen = new Set<string>()
  const items: TimelineItem[] = []

  for (const [index, event] of events.entries()) {
    const item = event as TimelineEvent & { title?: string; detail?: string }
    const title = titleCase(sanitizePath(toText(item.stage ?? item.event_type ?? item.type ?? item.title, "Analysis")) || "Analysis")
    const detail = sanitizeEvidenceDetail(item.message ?? item.detail ?? "Timeline event recorded.") || "Timeline event recorded."
    const key = `${title.toLowerCase()}|${detail.toLowerCase()}|${toText(item.timestamp ?? item.created_at)}`
    if (seen.has(key)) {
      continue
    }
    seen.add(key)

    const statusText = toText(item.status).toLowerCase()
    const status = statusText.includes("complete")
      ? "completed"
      : statusText.includes("run") || statusText.includes("active")
        ? "active"
        : "queued"

    items.push({
      id: createId(`timeline-${index}`),
      title,
      status,
      timestamp: toText(item.timestamp ?? item.created_at, new Date().toISOString()),
      detail,
    })
  }

  return items
}

export function normalizeDownloadError(error: unknown): string {
  const details = error && typeof error === "object" ? (error as { status?: unknown; message?: unknown }) : {}
  const status = typeof details.status === "number" ? details.status : undefined
  if (status === 404) {
    return "Reports are not available for this session yet."
  }
  if (status === 409 || status === 425 || status === 202) {
    return "Reports are available after analysis completes."
  }
  if (status === 500) {
    return "PDF generation failed. Try Markdown or JSON export, or check backend logs."
  }
  return toText(details.message, "Unable to download this report right now.")
}

export function summarizeSessionForFilename(sessionId: string): string {
  return truncateMiddle(sessionId, 6, 4).replace(/\.+/g, "-").replace(/[^a-zA-Z0-9-]/g, "")
}
