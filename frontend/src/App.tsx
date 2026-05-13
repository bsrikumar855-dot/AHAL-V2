import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom"
import { ConnectionBanner } from "./components/layout/ConnectionBanner"
import { AnimatedBackground } from "./components/ui/AnimatedBackground"
import { AnalyzePage } from "./pages/AnalyzePage"
import { ChatPage } from "./pages/ChatPage"
import { DashboardPage } from "./pages/DashboardPage"
import { DownloadsPage } from "./pages/DownloadsPage"
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage"
import { LandingPage } from "./pages/LandingPage"
import { LoginPage } from "./pages/LoginPage"
import { SignupPage } from "./pages/SignupPage"
import { SettingsPage } from "./pages/SettingsPage"

function AnimatedRoutes() {
  const location = useLocation()
  const reduceMotion = useReducedMotion()

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <Routes location={location}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/dashboard/:sessionId" element={<DashboardPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/downloads/:sessionId" element={<DownloadsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="relative min-h-screen">
        <AnimatedBackground />
        <ConnectionBanner />
        <AnimatedRoutes />
      </div>
    </BrowserRouter>
  )
}

export default App
