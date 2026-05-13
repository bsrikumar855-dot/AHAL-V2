import { motion } from "framer-motion"
import { Link, useNavigate } from "react-router-dom"
import { Mail, Lock, User, ArrowRight } from "lucide-react"
import { Button } from "../components/ui/Button"
import { Input } from "../components/ui/Input"
import { GlassCard } from "../components/ui/GlassCard"

export function SignupPage() {
  const navigate = useNavigate()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Signup logic would go here
    navigate("/login")
  }

  return (
    <div className="flex min-h-[calc(100vh-64px)] items-center justify-center px-4 py-20">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        <GlassCard className="p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <label htmlFor="name" className="text-sm font-medium text-slate-300">
                Full Name
              </label>
              <div className="relative">
                <User className="absolute left-4 top-3.5 h-5 w-5 text-slate-500" />
                <Input
                  id="name"
                  type="text"
                  placeholder="John Doe"
                  className="pl-12"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-slate-300">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-3.5 h-5 w-5 text-slate-500" />
                <Input
                  id="email"
                  type="email"
                  placeholder="name@example.com"
                  className="pl-12"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-slate-300">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-4 top-3.5 h-5 w-5 text-slate-500" />
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  className="pl-12"
                  required
                />
              </div>
            </div>

            <div className="pt-2">
              <Button type="submit" className="w-full" size="lg" icon={<ArrowRight className="h-5 w-5" />}>
                Get Started
              </Button>
            </div>
          </form>

          <div className="mt-8 text-center text-sm text-slate-400">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Log in instead
            </Link>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  )
}
