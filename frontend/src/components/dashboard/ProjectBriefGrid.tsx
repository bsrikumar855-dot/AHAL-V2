import { CheckCircle2, CircleAlert, Compass, Goal, Lightbulb, ListChecks } from "lucide-react"
import { humanizeCapability, safeText } from "../../lib/presentation"
import type { IntelligenceData } from "../../lib/types"
import { ConfidenceBadge } from "../ui/ConfidenceBadge"
import { GlassCard } from "../ui/GlassCard"

export function ProjectBriefGrid({ intelligence }: { intelligence: IntelligenceData }) {
  const whatText = safeText(intelligence.what, "") || "What the project does is only partially specified in the available output."
  const goalText = safeText(intelligence.projectGoal, "") || "Project goal was not provided in the returned intelligence."
  const repoType = String(intelligence.repoType || intelligence.projectType).toLowerCase()
  const isDocumentationRepo = ["documentation", "curriculum", "knowledge_base"].includes(repoType)
  const repoTypeLabel = repoType ? repoType.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()) : "Unknown"

  return (
    <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
      <GlassCard glow className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
            <Goal className="h-5 w-5 text-cyan-200" />
          </div>
          <div>
            <p className="text-sm text-slate-400">Project Goal</p>
            <h3 className="text-xl font-semibold text-white">{intelligence.projectName || "Analyzed Project"}</h3>
            <p className="mt-1 text-xs uppercase tracking-[0.2em] text-cyan-200/75">{repoTypeLabel}</p>
          </div>
        </div>
        <p className="text-base leading-8 text-slate-200">{goalText}</p>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">{isDocumentationRepo ? "Repository Structure Confidence" : "Architecture Confidence"}</p>
            <div className="mt-3"><ConfidenceBadge value={intelligence.architectureConfidence} /></div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
            <p className="text-sm text-slate-400">Product Purpose Confidence</p>
            <div className="mt-3"><ConfidenceBadge value={intelligence.productPurposeConfidence} /></div>
          </div>
        </div>
      </GlassCard>

      <div className="grid gap-5">
        <GlassCard>
          <div className="flex items-center gap-3">
            <Compass className="h-5 w-5 text-violet-200" />
            <h3 className="text-lg font-semibold text-white">What</h3>
          </div>
          <p className="mt-4 break-words text-sm leading-7 text-slate-300">{safeText(whatText, "What the project does is only partially specified in the available output.")}</p>
        </GlassCard>
        <GlassCard>
          <div className="flex items-center gap-3">
            <Lightbulb className="h-5 w-5 text-amber-200" />
            <h3 className="text-lg font-semibold text-white">Why</h3>
          </div>
          <p className="mt-4 break-words text-sm leading-7 text-slate-300">{safeText(intelligence.why, "Why the project exists was not fully returned by the backend.")}</p>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-200" />
          <h3 className="text-lg font-semibold text-white">Completed</h3>
        </div>
        <div className="mt-5 space-y-4">
          {intelligence.completed.length ? intelligence.completed.map((item, index) => (
            <div key={item.title} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <p className="font-medium text-white">{humanizeCapability(item.title || item.description || `Detected capability ${index + 1}`)}</p>
              <p className="mt-2 break-words text-sm text-slate-400">{safeText(item.description, "Capability details were not returned.")}</p>
            </div>
          )) : <p className="text-sm text-slate-400">No completed capabilities were returned for this session.</p>}
        </div>
      </GlassCard>

      <GlassCard>
        <div className="flex items-center gap-3">
          <ListChecks className="h-5 w-5 text-cyan-200" />
          <h3 className="text-lg font-semibold text-white">Remaining</h3>
        </div>
        <div className="mt-5 space-y-4">
          {intelligence.remaining.length ? intelligence.remaining.map((item) => (
            <div key={item.title} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <p className="font-medium text-white">{humanizeCapability(item.title || item.description)}</p>
              <p className="mt-2 break-words text-sm text-slate-400">{safeText(item.description, "Remaining work details were not returned.")}</p>
            </div>
          )) : <p className="text-sm text-slate-400">No remaining work items were returned for this session.</p>}
        </div>
      </GlassCard>

      <GlassCard className="xl:col-span-2">
        <div className="flex items-center gap-3">
          <CircleAlert className="h-5 w-5 text-rose-200" />
          <h3 className="text-lg font-semibold text-white">Issues & Warnings</h3>
        </div>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            {intelligence.issues.length ? intelligence.issues.map((item) => (
              <div key={item.title} className="rounded-2xl border border-rose-400/15 bg-rose-500/10 p-4">
                <p className="font-medium text-white">{humanizeCapability(item.title)}</p>
                <p className="mt-2 break-words text-sm text-rose-100/80">{safeText(item.recommendation, "Issue details were not returned.")}</p>
              </div>
            )) : <p className="text-sm text-slate-400">No critical issues returned for this session.</p>}
          </div>
          <div className="space-y-3">
            {intelligence.warnings.length ? intelligence.warnings.map((warning) => (
              <div key={warning} className="rounded-2xl border border-amber-400/15 bg-amber-500/10 p-4 text-sm text-amber-100/85">
                {safeText(warning, "Warning returned by backend.")}
              </div>
            )) : <p className="text-sm text-slate-400">No critical issues returned for this session.</p>}
          </div>
        </div>
      </GlassCard>
    </div>
  )
}
