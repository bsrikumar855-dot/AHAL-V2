import { useState } from "react"
import { motion } from "framer-motion"
import { Link } from "react-router-dom"
import { ArrowRight, CheckCircle2, Mail, ShieldCheck } from "lucide-react"
import { Button } from "../components/ui/Button"
import { Input } from "../components/ui/Input"
import { GlassCard } from "../components/ui/GlassCard"

export function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
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
          <div className="mb-6 space-y-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-400/10 text-cyan-300">
              {submitted ? <CheckCircle2 className="h-6 w-6" /> : <ShieldCheck className="h-6 w-6" />}
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-white">
                {submitted ? "Check your email" : "Forgot password?"}
              </h1>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                {submitted
                  ? "If the email address exists in our system, we sent a password reset link with next steps."
                  : "Enter your email address and we'll send a reset link so you can get back into your account."}
              </p>
            </div>
          </div>

          {submitted ? (
            <div className="space-y-5">
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/5 p-4 text-sm text-slate-300">
                Didn't get the message? Check your spam folder or try again in a few minutes.
              </div>

              <Link
                to="/login"
                className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500 px-6 text-base font-medium text-slate-950 shadow-[0_12px_32px_rgba(56,189,248,0.28)] transition hover:brightness-110"
              >
                Back to sign in
                <ArrowRight className="h-5 w-5" />
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
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

              <Button type="submit" className="w-full" size="lg" icon={<ArrowRight className="h-5 w-5" />}>
                Send reset link
              </Button>
            </form>
          )}

          <div className="mt-8 text-center text-sm text-slate-400">
            Remember your password?{" "}
            <Link to="/login" className="font-semibold text-cyan-400 transition-colors hover:text-cyan-300">
              Log in instead
            </Link>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  )
}
