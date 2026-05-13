import { BotMessageSquare, Download, Home, LayoutDashboard, SearchCode, Settings } from "lucide-react"
import { NavLink } from "react-router-dom"
import { cn } from "../../lib/utils"

type SidebarProps = {
  sessionId?: string
}

const items = [
  { to: "/", label: "Home", icon: Home },
  { to: "/analyze", label: "Analyze", icon: SearchCode },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, sessionAware: true },
  { to: "/chat", label: "Repo Chat", icon: BotMessageSquare, sessionAware: true },
  { to: "/downloads", label: "Downloads", icon: Download, sessionAware: true },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function Sidebar({ sessionId }: SidebarProps) {
  return (
    <>
      <aside className="hidden w-[270px] shrink-0 flex-col border-r border-white/8 bg-slate-950/40 p-6 backdrop-blur-xl lg:flex">
        <NavLink to="/" className="mb-10 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center overflow-hidden rounded-2xl bg-white p-1">
            <img src="/brand-logo.png" alt="AHAL AI Logo" className="h-full w-full object-contain" />
          </div>
          <div>
            <p className="text-base font-semibold uppercase tracking-[0.26em] text-cyan-300/70">AHAL AI</p>
          </div>
        </NavLink>

        <nav className="space-y-2">
          {items.map((item) => {
            const href = item.sessionAware ? (sessionId ? `${item.to}/${sessionId}` : item.to) : item.to
            const Icon = item.icon
            return (
              <NavLink
                key={item.label}
                to={href}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm text-slate-400 transition hover:bg-white/[0.06] hover:text-white",
                    isActive && "bg-white/[0.08] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        <div className="mt-auto rounded-3xl border border-white/10 bg-white/[0.04] p-5">
          <p className="text-sm font-medium text-white">Validated project intelligence</p>
          <p className="mt-2 text-sm text-slate-400">
            Analyze repositories, generate reports, and keep engineering context grounded in evidence.
          </p>
        </div>
      </aside>

      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-white/10 bg-slate-950/90 px-2 py-2 backdrop-blur-xl lg:hidden">
        {items.map((item) => {
          const href = item.sessionAware ? (sessionId ? `${item.to}/${sessionId}` : item.to) : item.to
          const Icon = item.icon
          return (
            <NavLink
              key={item.label}
              to={href}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center justify-center gap-1 rounded-2xl px-1 py-2 text-[10px] text-slate-400 transition",
                  isActive && "bg-white/[0.08] text-white",
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>
    </>
  )
}
