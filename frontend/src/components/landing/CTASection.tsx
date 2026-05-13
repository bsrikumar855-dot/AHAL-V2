import { Link } from "react-router-dom"
import { Button } from "../ui/Button"
import { GlassCard } from "../ui/GlassCard"
import { SectionHeader } from "../ui/SectionHeader"

export function CTASection() {
  return (
    <section className="px-4 pb-24 pt-10 md:px-8">
      <div className="mx-auto max-w-7xl">
        <GlassCard glow className="overflow-hidden">
          <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
            <SectionHeader
              eyebrow="Get Started"
              title="Bring your next repository review into one animated, evidence-grounded workspace"
              description="Start with a snippet, a folder, or a GitHub repository and move directly into validated project intelligence."
            />
            <div className="flex flex-col gap-3 sm:flex-row lg:flex-col">
              <Link to="/login">
                <Button size="lg">Start Analyzing</Button>
              </Link>
            </div>
          </div>
        </GlassCard>
      </div>
    </section>
  )
}
