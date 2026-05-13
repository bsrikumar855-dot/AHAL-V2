import { ArrowRight, FileCode2, GitBranchPlus, MessageSquareQuote, TestTube2 } from "lucide-react"
import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { Button } from "../ui/Button"
import { GlassCard } from "../ui/GlassCard"
import { MagneticButton } from "../ui/MagneticButton"
import { ScrollReveal } from "../ui/ScrollReveal"

const floatingCards = [
  { title: "Architecture Diff", icon: GitBranchPlus, accent: "from-cyan-400/30 to-transparent" },
  { title: "Test Gaps", icon: TestTube2, accent: "from-emerald-400/30 to-transparent" },
  { title: "Repo Chat", icon: MessageSquareQuote, accent: "from-violet-400/30 to-transparent" },
  { title: "PDF Report", icon: FileCode2, accent: "from-blue-400/30 to-transparent" },
]

export function HeroSection() {
  return (
    <section className="relative overflow-hidden px-4 pb-20 pt-24 md:px-8 md:pt-32">
      <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[1.12fr_0.88fr] lg:items-center">
        <ScrollReveal className="space-y-8">

          <div className="space-y-6">
            <h1 className="max-w-4xl text-5xl font-semibold tracking-[-0.04em] text-white md:text-7xl">
              <span className="block">AHAL AI</span>
              <span className="block text-gradient">Turn any codebase into validated project intelligence.</span>
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-300">
              Analyze code, folders, and GitHub repositories. Generate architecture summaries, repo chat, onboarding guides,
              test gap reports, PRD/PDF documentation, and architecture diffs.
            </p>
          </div>

          <div className="flex flex-col gap-4 sm:flex-row">
            <MagneticButton>
              <Link to="/login">
                <Button size="lg" icon={<ArrowRight className="h-4 w-4" />}>Start Analyzing</Button>
              </Link>
            </MagneticButton>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={0.1} direction="left">
          <div className="relative">
            <GlassCard glow className="relative overflow-hidden p-0">
              <div className="border-b border-white/10 bg-white/[0.04] px-6 py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-cyan-300/70">Command Preview</p>
                    <h2 className="mt-2 text-xl font-semibold text-white">Repository intelligence cockpit</h2>
                  </div>
                  <div className="flex gap-2">
                    <span className="h-3 w-3 rounded-full bg-rose-400/80" />
                    <span className="h-3 w-3 rounded-full bg-amber-300/80" />
                    <span className="h-3 w-3 rounded-full bg-emerald-300/80" />
                  </div>
                </div>
              </div>

              <div className="space-y-6 p-6">
                <div className="rounded-3xl border border-white/10 bg-slate-950/70 p-5 font-mono text-sm text-cyan-100">
                  <p className="text-slate-500">$ ahal analyze --repo github.com/acme/platform</p>
                  <p className="mt-3">Fact extraction complete.</p>
                  <p className="mt-1 text-violet-200">Truth layer validated the architecture summary and product purpose.</p>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  {floatingCards.map((card, index) => {
                    const Icon = card.icon
                    return (
                      <motion.div
                        key={card.title}
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 + index * 0.1, duration: 0.45 }}
                        className={`rounded-3xl border border-white/10 bg-gradient-to-br ${card.accent} via-white/[0.05] to-white/[0.02] p-5`}
                      >
                        <Icon className="h-5 w-5 text-cyan-200" />
                        <p className="mt-6 text-sm text-slate-300">{card.title}</p>
                      </motion.div>
                    )
                  })}
                </div>
              </div>
            </GlassCard>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}
