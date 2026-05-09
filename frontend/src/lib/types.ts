export type ConfidenceLevel = "High" | "Medium" | "Low"
export type ProjectType =
  | "frontend"
  | "backend"
  | "fullstack"
  | "documentation"
  | "curriculum"
  | "knowledge_base"
  | "mobile_app"
  | "cli_tool"
  | "python_package"
  | "npm_package"
  | "component_library"
  | "sdk"
  | "plugin"
  | "browser_extension"
  | "vscode_extension"
  | "ml_model_repo"
  | "data_science_notebooks"
  | "dataset"
  | "template"
  | "infrastructure"
  | "devops_automation"
  | "design_assets"
  | "research_code"
  | "monorepo"
  | "mixed"
  | "unknown"

export interface SessionInfo {
  sessionId: string | null
  accessToken: string | null
}

export interface SessionResponse {
  session_id: string
  access_token?: string
  status?: string
  message?: string
}

export interface StatusResponse {
  session_id?: string
  status: "queued" | "running" | "completed" | "failed" | string
  error?: string
  progress?: number
  message?: string
  stage?: string
}

export interface IntelligenceResponse {
  session_id?: string
  project_name?: string
  project_goal?: string
  project_type?: string
  repo_visibility?: string
  hallucination_risk?: string
  architecture_style?: string
  architecture_confidence?: string
  product_purpose_confidence?: string
  key_modules?: Array<string | { name?: string; category?: string; description?: string }>
  core_features?: string[]
  risks?: Array<string | { title?: string; severity?: string; recommendation?: string }>
  summary?: {
    what?: string
    why?: string
    remaining?: string[]
    issues?: string[]
  }
  technical?: {
    tech_stack?: Array<string | { category?: string; items?: string[] }>
    api_surface?: Array<Record<string, unknown>>
    workflow?: Array<Record<string, unknown>>
    database?: string[]
  }
  evidence?: Array<Record<string, unknown>>
  warnings?: string[]
  confidence?: "high" | "medium" | "low" | string
  canonical_intelligence?: CanonicalIntelligenceResponse
}

export interface CanonicalIntelligenceResponse {
  session_id?: string
  project_name?: string
  project_type?: string
  repo_type?: string
  repo_visibility?: string
  hallucination_risk?: string
  product_summary?: string
  project_goal?: string
  product_domain?: string
  architecture_summary?: string
  what?: string
  why?: string
  completed?: Array<{ title?: string; description?: string; confidence?: string }>
  remaining?: Array<{ title?: string; description?: string; confidence?: string }>
  issues?: Array<{ severity?: string; title?: string; recommendation?: string }>
  tech_stack?: {
    languages?: string[]
    frameworks?: string[]
    databases?: string[]
    tools?: string[]
  }
  api_surface?: Array<{ method?: string; path?: string; purpose?: string; source?: string }>
  workflow?: Array<{ step?: number; title?: string; description?: string }>
  evidence?: Array<{ id?: string; label?: string; reason?: string; source_type?: string; confidence?: string }>
  warnings?: string[]
  confidence?: {
    architecture?: string
    product_purpose?: string
    overall?: string
  }
  data_quality?: {
    normalized?: boolean
    notes?: string[]
  }
}

export interface TimelineEvent {
  event_type?: string
  type?: string
  message?: string
  status?: string
  timestamp?: string
  created_at?: string
  stage?: string
  metadata?: Record<string, string>
}

export interface TimelineResponse {
  session_id?: string
  events?: TimelineEvent[]
}

export interface BackendChatResponse {
  answer: string
  short_answer?: string
  sections?: Array<{
    title?: string
    content?: string
    bullets?: string[]
    evidence_ids?: string[]
  }>
  confidence?: string
  evidence?: Array<Record<string, unknown>>
  warnings?: string[]
  suggested_followups?: string[]
  intent?: string
  used_llm?: boolean
  fallback_used?: boolean
}

export interface TestGapResponse {
  summary?: string
  warnings?: string[]
  gaps?: Array<Record<string, unknown>>
}

export interface OnboardingResponse {
  summary?: string
  reading_order?: Array<Record<string, unknown>>
  warnings?: string[]
  gotchas?: string[]
}

export interface RepoIndexResponse {
  index_id: string
  session_id?: string
  status?: string
  source_name?: string
  warnings?: string[]
}

export interface DeltaScanResponse {
  index_id?: string
  base_session_id?: string
  new_session_id?: string
  summary?: string
  warnings?: string[]
  confidence?: string
}

export interface PrdDiffResponse {
  summary?: string
  changes?: Array<Record<string, unknown>>
}

export interface HealthResponse {
  ok?: boolean
  status?: string
  service?: string
  version?: string
}

export interface LlmStatusResponse {
  llm_enabled: boolean
  chat_llm_enabled: boolean
  docs_llm_enabled: boolean
  model: string
  provider?: string
  key_present: boolean
  last_error_type?: string | null
  fallback_count?: number
  rate_limited_until?: number | null
  warnings?: string[]
}

export interface AnalyzeCodePayload {
  filename: string
  language: string
  code: string
}

export interface AnalyzeResponse {
  sessionId: string
  accessToken?: string
  message?: string
  demoMode?: boolean
}

export interface TechStackCategory {
  category: string
  items: string[]
}

export interface NormalizedTechStack {
  languages: string[]
  frameworks: string[]
  databases: string[]
  tools: string[]
}

export interface ApiSurfaceItem {
  method: string
  path: string
  source: string
  purpose: string
}

export interface WorkflowStep {
  title: string
  description: string
}

export interface IssueItem {
  severity: string
  title: string
  recommendation: string
}

export interface EvidenceItem {
  label: string
  detail?: string
}

export interface TimelineItem {
  id: string
  title: string
  status: "completed" | "active" | "queued"
  timestamp: string
  detail: string
}

export interface BriefItem {
  title: string
  description: string
}

export interface NormalizedIntelligence {
  projectName: string
  projectType: ProjectType
  repoType?: string
  repoVisibility: "Public" | "Private" | "Unknown"
  hallucinationRisk: "High" | "Medium" | "Low" | "Unknown"
  architectureConfidence: ConfidenceLevel | "Unknown"
  productPurposeConfidence: ConfidenceLevel | "Unknown"
  projectGoal: string
  projectSummary: string
  what: string
  why: string
  completed: BriefItem[]
  remaining: BriefItem[]
  issues: IssueItem[]
  techStack: NormalizedTechStack
  apiSurface: ApiSurfaceItem[]
  workflow: WorkflowStep[]
  evidence: EvidenceItem[]
  warnings: string[]
  sessionId?: string
  dataQuality: {
    normalized: boolean
    notes: string[]
  }
}

export type IntelligenceData = NormalizedIntelligence

export interface RiskItem {
  severity: "High" | "Medium" | "Low"
  issue: string
  recommendation: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: string
  confidence?: ConfidenceLevel
  warnings?: string[]
  evidence?: EvidenceItem[]
  shortAnswer?: string
  sections?: ChatAnswerSection[]
  suggestedFollowups?: string[]
  intent?: string
  usedLlm?: boolean
  fallbackUsed?: boolean
}

export interface ChatAnswerSection {
  title: string
  content: string
  bullets: string[]
  evidenceIds: string[]
}

export interface ChatResponse {
  message: ChatMessage
  suggestedQuestions: string[]
  demoMode?: boolean
}

export interface NormalizedChatResponse {
  message: ChatMessage
  suggestedQuestions: string[]
}

export interface TestGapItem {
  area: string
  gap: string
  impact: string
}

export interface TestGapReport {
  summary: string
  items: TestGapItem[]
  warnings?: string[]
}

export interface OnboardingStep {
  title: string
  detail: string
}

export interface OnboardingReport {
  summary: string
  steps: OnboardingStep[]
  warnings?: string[]
}

export interface DiffItem {
  title: string
  detail: string
}

export interface PrdDiffResult {
  summary: string
  changes: DiffItem[]
}

export interface ApiResult<T> {
  data: T
  demoMode: boolean
}
