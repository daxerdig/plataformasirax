'use client'

import React, { useState, useEffect, useRef, useCallback, createContext, useContext } from 'react'
import {
  motion,
  useScroll,
  useTransform,
  useSpring,
  useInView,
  AnimatePresence,
  useMotionValue,
  animate,
} from 'framer-motion'
import {
  ShieldCheck, ArrowRight, IdCard, Scale, Globe2, Network,
  Brain, BarChart3, Plug, Lock, Eye, CheckCircle2, ChevronRight,
  FileSearch, ShieldAlert, TrendingUp, AlertTriangle, XCircle,
  Search, Phone, Mail, User, MapPin, Calendar, Hash,
  ChevronLeft, Activity, Database, ExternalLink, Copy, RefreshCw,
  Menu, X, LogOut, Plus, Filter, Download, Zap, Target,
  GitBranch, Linkedin, Github, Instagram, Twitter, MessageCircle,
  BookOpen, Code2, Building2, Flag, Sparkles, Radar, Cpu, Layers,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, Legend, LineChart, Line,
  AreaChart, Area,
  ResponsiveContainer, RadialBarChart, RadialBar,
} from 'recharts'
import { useToast } from '@/hooks/use-toast'
import { generateCheckPDF } from '@/lib/generate-pdf'

// ==================== API Helper ====================
const API = {
  get: async (path: string, token?: string | null) => {
    const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    return res.json()
  },
  post: async (path: string, body: any, token?: string | null) => {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body),
    })
    return res.json()
  },
  del: async (path: string, token: string | null) => {
    const res = await fetch(path, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    return res.json()
  },
}

// ==================== Auth Context ====================
type User = { id: string; email: string; full_name: string; role: string; organization?: string }

const AuthContext = createContext<{
  user: User | null; token: string | null; login: (t: string, u: User) => void; logout: () => void
}>({ user: null, token: null, login: () => {}, logout: () => {} })

function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Read from localStorage on mount - this is the only safe place
    const t = localStorage.getItem('sirax_token')
    const u = localStorage.getItem('sirax_user')
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hidratación única desde localStorage al montar
    if (t) setToken(t)
    if (u) {
      try { setUser(JSON.parse(u)) } catch {}
    }
    setReady(true)
  }, [])

  const login = (t: string, u: User) => {
    localStorage.setItem('sirax_token', t)
    localStorage.setItem('sirax_user', JSON.stringify(u))
    setToken(t); setUser(u)
  }

  const logout = () => {
    localStorage.removeItem('sirax_token')
    localStorage.removeItem('sirax_user')
    localStorage.removeItem('sirax_view')
    setToken(null); setUser(null)
  }

  // Show nothing during SSR/hydration to avoid mismatch
  if (!ready) {
    return <div className="min-h-screen bg-white" />
  }

  return <AuthContext.Provider value={{ user, token, login, logout }}>{children}</AuthContext.Provider>
}

function useAuth() { return useContext(AuthContext) }

// Helper to get token - falls back to localStorage if context token is null
function useToken(): string | null {
  const { token } = useAuth()
  if (token) return token
  if (typeof window !== 'undefined') {
    return localStorage.getItem('sirax_token') || localStorage.getItem('synkdata_token')
  }
  return null
}

// ==================== View Router ====================
type View = 'landing' | 'login' | 'register' | 'dashboard' | 'new-check' | 'history' | 'check-results' | 'curp' | 'rfc' | 'sanctions' | 'api-docs'

const RouterContext = createContext<{ view: View; navigate: (v: View, data?: any) => void; viewData: any }>({
  view: 'landing', navigate: () => {}, viewData: null
})

function useRouter() { return useContext(RouterContext) }

// ==================== Constants ====================
const RISK_COLORS: Record<string, string> = { BAJO: '#00d1a0', MEDIO: '#f59e0b', ALTO: '#ef4444', CRITICO: '#9f1239' }
const REC_COLORS: Record<string, string> = { APPROVE: '#00d1a0', REVIEW: '#f59e0b', REJECT: '#ef4444' }
const REC_LABEL: Record<string, string> = { APPROVE: 'Aprobar', REVIEW: 'Revisar', REJECT: 'Rechazar' }

// ==================== Sirax Logo ====================
function SiraxMark({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {/* Connecting lines (dashed teal) */}
      <g
        stroke="#00D1A0"
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray="6 5"
        opacity="0.9"
      >
        <line x1="50" y1="50" x2="18" y2="18" />
        <line x1="50" y1="50" x2="82" y2="18" />
        <line x1="50" y1="50" x2="18" y2="82" />
        <line x1="50" y1="50" x2="82" y2="82" />
      </g>
      {/* Center node */}
      <circle cx="50" cy="50" r="7" fill="currentColor" />
      {/* Outer nodes */}
      <circle cx="18" cy="18" r="5" fill="#00D1A0" />
      <circle cx="82" cy="18" r="5" fill="#00D1A0" />
      <circle cx="18" cy="82" r="5" fill="#00D1A0" />
      <circle cx="82" cy="82" r="5" fill="#00D1A0" />
    </svg>
  )
}

function SiraxWordmark({
  className = '',
  showTagline = false,
}: {
  className?: string
  showTagline?: boolean
}) {
  return (
    <span className={`inline-flex flex-col leading-none ${className}`}>
      <span className="sirax-wordmark text-current">
        s
        <span style={{ position: 'relative', display: 'inline-block' }}>
          <span className="i-dot" />
          <span style={{ opacity: 0 }}>i</span>
          <span style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 }} />
        </span>
        ra
        <span className="x-teal">x</span>
      </span>
      {showTagline && (
        <span className="text-[10px] uppercase tracking-[0.22em] text-current/60 mt-1.5 font-medium">
          Identity & Risk Intelligence
        </span>
      )}
    </span>
  )
}

function SiraxLogo({
  size = 32,
  variant = 'light',
  showTagline = false,
  className = '',
}: {
  size?: number
  variant?: 'light' | 'dark'
  showTagline?: boolean
  className?: string
}) {
  // variant 'light' = for navy backgrounds (white text)
  // variant 'dark'  = for white backgrounds (navy text)
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className={variant === 'light' ? 'text-white' : 'text-sirax-navy'}>
        <SiraxMark size={size} />
      </span>
      <span className={`flex flex-col leading-none ${variant === 'light' ? 'text-white' : 'text-sirax-navy'}`}>
        <SiraxWordmark />
        {showTagline && (
          <span className="text-[9px] uppercase tracking-[0.24em] opacity-60 mt-1 font-medium">
            a Synkdata product
          </span>
        )}
      </span>
    </span>
  )
}

// ==================== Particle Field (Hero background) ====================
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const mouseRef = useRef({ x: -9999, y: -9999 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    let width = 0
    let height = 0
    let dpr = 1

    type P = { x: number; y: number; vx: number; vy: number }
    let particles: P[] = []

    const resize = () => {
      const parent = canvas.parentElement
      if (!parent) return
      const rect = parent.getBoundingClientRect()
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = width + 'px'
      canvas.style.height = height + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.min(70, Math.floor((width * height) / 18000))
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
      }))
    }

    const draw = () => {
      ctx.clearRect(0, 0, width, height)
      const linkDist = 140
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > width) p.vx *= -1
        if (p.y < 0 || p.y > height) p.vy *= -1

        // mouse repulsion
        const dxm = p.x - mouseRef.current.x
        const dym = p.y - mouseRef.current.y
        const dm = Math.hypot(dxm, dym)
        if (dm < 120) {
          p.x += (dxm / dm) * 0.6
          p.y += (dym / dm) * 0.6
        }

        ctx.beginPath()
        ctx.arc(p.x, p.y, 1.6, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(0, 209, 160, 0.55)'
        ctx.fill()
      }
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i]
          const b = particles[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d = Math.hypot(dx, dy)
          if (d < linkDist) {
            const op = (1 - d / linkDist) * 0.22
            ctx.strokeStyle = `rgba(0, 209, 160, ${op})`
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }
      raf = requestAnimationFrame(draw)
    }

    resize()
    draw()
    window.addEventListener('resize', resize)

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }
    const onLeave = () => {
      mouseRef.current = { x: -9999, y: -9999 }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseout', onLeave)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseout', onLeave)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />
}

// ==================== Scroll Reveal ====================
function Reveal({
  children,
  delay = 0,
  y = 24,
  className = '',
}: {
  children: React.ReactNode
  delay?: number
  y?: number
  className?: string
}) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// ==================== Animated Counter ====================
function Counter({
  to,
  suffix = '',
  prefix = '',
  decimals = 0,
}: {
  to: number
  suffix?: string
  prefix?: string
  decimals?: number
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const [val, setVal] = useState(0)

  useEffect(() => {
    if (!inView) return
    const controls = animate(0, to, {
      duration: 1.6,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setVal(v),
    })
    return () => controls.stop()
  }, [inView, to])

  return (
    <span ref={ref}>
      {prefix}
      {val.toFixed(decimals)}
      {suffix}
    </span>
  )
}

// ==================== Landing Module Card ====================
function LandingModule({
  icon: Icon,
  title,
  desc,
  items,
  index,
}: {
  icon: any
  title: string
  desc: string
  items: string[]
  index: number
}) {
  return (
    <Reveal delay={index * 0.05}>
      <motion.div
        whileHover={{ y: -4 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        className="group relative h-full p-6 bg-white border border-white/8 rounded-xl hover:border-sirax-teal transition-colors overflow-hidden"
      >
        <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-sirax-teal-soft opacity-0 group-hover:opacity-100 blur-2xl transition-opacity duration-500" />
        <div className="relative">
          <div className="flex items-center justify-between mb-4">
            <div className="h-11 w-11 bg-sirax-navy text-white flex items-center justify-center rounded-lg group-hover:bg-sirax-teal group-hover:text-white transition-colors">
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            </div>
            <ChevronRight className="h-4 w-4 text-white/55 group-hover:text-sirax-teal group-hover:translate-x-1 transition-all" />
          </div>
          <h3 className="font-bold text-slate-950 text-lg mb-2">{title}</h3>
          <p className="text-sm text-white/45 mb-4 leading-relaxed">{desc}</p>
          <ul className="space-y-1.5">
            {items.map((it: string) => (
              <li key={it} className="text-xs text-white/60 font-mono flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-sirax-teal" />
                {it}
              </li>
            ))}
          </ul>
        </div>
      </motion.div>
    </Reveal>
  )
}

// ==================== Landing Page ====================
function LandingView() {
  const { navigate } = useRouter()
  const { user } = useAuth()

  // Hero parallax
  const heroRef = useRef<HTMLDivElement | null>(null)
  const { scrollYProgress: heroProgress } = useScroll({
    target: heroRef,
    offset: ['start start', 'end start'],
  })
  const heroY = useTransform(heroProgress, [0, 1], [0, 140])
  const heroOpacity = useTransform(heroProgress, [0, 0.8], [1, 0])
  const heroScale = useTransform(heroProgress, [0, 1], [1, 0.96])

  // Stats marquee — pause on hover handled via group-hover
  const coverageSources = [
    'RENAPO', 'SAT', 'IMSS', 'RND', 'OFAC', 'ONU',
    'OpenSanctions', 'SAT 69-B', 'Interpol', 'EU Consolidated',
    'UK HMT', 'HaveIBeenPwned', 'Hunter.io', 'NumVerify',
    'Sherlock', 'Maigret', 'DOF', 'SCJN',
  ]

  return (
    <div className="min-h-screen bg-white">
      {/* Nav */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="fixed top-0 inset-x-0 z-50 bg-white/80 backdrop-blur-md border-b border-white/8"
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <button onClick={() => navigate('landing')} className="flex items-center">
            <SiraxLogo size={30} variant="dark" showTagline />
          </button>
          <nav className="hidden md:flex items-center gap-8 text-sm text-white/60">
            <a href="#modules" className="hover:text-white transition-colors">Plataforma</a>
            <a href="#coverage" className="hover:text-white transition-colors">Cobertura</a>
            <a href="#api" className="hover:text-white transition-colors">API</a>
            <button onClick={() => navigate('api-docs')} className="hover:text-white transition-colors">Docs</button>
          </nav>
          <div className="flex items-center gap-3">
            {user ? (
              <motion.button
                whileHover={{ y: -1 }}
                onClick={() => navigate('dashboard')}
                className="text-sm font-semibold bg-sirax-navy text-white px-4 py-2 rounded-md hover:bg-sirax-navy-soft transition-colors"
              >
                Ir al Dashboard
              </motion.button>
            ) : (
              <>
                <button onClick={() => navigate('login')} className="text-sm font-medium text-white/60 hover:text-white">
                  Iniciar sesión
                </button>
                <motion.button
                  whileHover={{ y: -1 }}
                  onClick={() => navigate('register')}
                  className="text-sm font-semibold bg-sirax-navy text-white px-4 py-2 rounded-md hover:bg-sirax-navy-soft transition-colors"
                >
                  Crear cuenta
                </motion.button>
              </>
            )}
          </div>
        </div>
      </motion.header>

      {/* Hero */}
      <section
        ref={heroRef}
        className="relative bg-sirax-navy text-white pt-32 pb-24 overflow-hidden"
      >
        {/* Background layers */}
        <div className="absolute inset-0 sirax-grid opacity-60" />
        <ParticleField />
        <div className="absolute -top-40 -right-40 w-[28rem] h-[28rem] bg-sirax-teal/15 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-[28rem] h-[28rem] bg-sirax-teal/10 rounded-full blur-3xl" />

        <motion.div
          style={{ y: heroY, opacity: heroOpacity, scale: heroScale }}
          className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-12 gap-12"
        >
          <div className="lg:col-span-7">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5 text-xs font-medium text-white/55 mb-6 backdrop-blur"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inset-0 rounded-full bg-sirax-teal animate-ping opacity-75" />
                <span className="relative rounded-full bg-sirax-teal h-1.5 w-1.5" />
              </span>
              Plataforma operativa · México y LATAM
            </motion.div>

            <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold tracking-tighter leading-[1.02] mb-6">
              <motion.span
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 0.15 }}
                className="block"
              >
                Know More.
              </motion.span>
              <motion.span
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 0.28 }}
                className="block sirax-gradient-text"
              >
                Risk Less.
              </motion.span>
            </h1>

            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.4 }}
              className="text-base sm:text-lg text-white/40 max-w-xl mb-8 leading-relaxed"
            >
              sirax centraliza fuentes gubernamentales, listas regulatorias internacionales,
              inteligencia digital y análisis relacional para entregar una visión completa de
              identidad y riesgo en segundos.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.5 }}
              className="flex flex-wrap items-center gap-3"
            >
              <motion.button
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate(user ? 'dashboard' : 'register')}
                className="inline-flex items-center gap-2 bg-sirax-teal text-sirax-navy px-5 py-3 rounded-md font-semibold text-sm hover:bg-sirax-teal-bright transition-colors"
              >
                Comenzar ahora <ArrowRight className="h-4 w-4" />
              </motion.button>
              <motion.button
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate('login')}
                className="inline-flex items-center gap-2 border border-white/15 px-5 py-3 rounded-md font-semibold text-sm hover:bg-white/5 transition-colors"
              >
                Acceder a la consola
              </motion.button>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.62 }}
              className="mt-14 grid grid-cols-3 gap-6 max-w-md"
            >
              {[
                { v: 15, suffix: '+', l: 'Fuentes integradas' },
                { v: 2, prefix: '<', suffix: 's', l: 'Tiempo de respuesta' },
                { v: 99.9, suffix: '%', decimals: 1, l: 'Disponibilidad' },
              ].map((s) => (
                <div key={s.l}>
                  <div className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
                    <Counter to={s.v} prefix={s.prefix} suffix={s.suffix} decimals={s.decimals || 0} />
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/45 mt-1.5">
                    {s.l}
                  </div>
                </div>
              ))}
            </motion.div>
          </div>

          {/* Hero card */}
          <div className="lg:col-span-5 relative">
            <motion.div
              initial={{ opacity: 0, scale: 0.94, rotate: -2 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 0.9, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="relative rounded-2xl border border-white/10 bg-sirax-navy-soft/70 backdrop-blur-sm p-5 shadow-2xl"
            >
              {/* Glow */}
              <div className="absolute -inset-1 sirax-glow-teal opacity-40 -z-10 rounded-2xl" />

              <div className="flex items-center justify-between mb-4">
                <div className="text-[10px] uppercase tracking-[0.2em] text-white/45">
                  Live demo · Trust Score
                </div>
                <div className="flex items-center gap-1 text-[10px] text-sirax-teal font-mono">
                  <span className="h-1.5 w-1.5 rounded-full bg-sirax-teal sirax-pulse-dot" />
                  live
                </div>
              </div>

              <div className="flex items-end gap-6 mb-5">
                <motion.div
                  initial={{ opacity: 0, scale: 0.7 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.8, delay: 0.7, type: 'spring' }}
                  className="text-7xl font-extrabold tracking-tighter bg-gradient-to-br from-white to-sirax-teal bg-clip-text text-transparent"
                >
                  92
                </motion.div>
                <div>
                  <div className="px-2 py-0.5 rounded text-xs font-bold bg-sirax-teal text-sirax-navy">
                    BAJO RIESGO
                  </div>
                  <div className="text-xs text-white/40 mt-1.5">Recomendación: APROBAR</div>
                </div>
              </div>

              <div className="space-y-2.5 text-xs">
                {[
                  ['CURP', 'Verificado RENAPO'],
                  ['RFC', 'Activo en SAT'],
                  ['OFAC / ONU', 'Sin coincidencias'],
                  ['RND', 'Sin registros'],
                  ['Email', 'Corporativo · 0 brechas'],
                  ['LinkedIn', 'Perfil profesional'],
                  ['GitHub', 'Cuenta activa · 4 años'],
                ].map(([k, v], i) => (
                  <motion.div
                    key={k}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, delay: 0.8 + i * 0.08 }}
                    className="flex items-center justify-between p-2 rounded-md border border-white/5 bg-white/[0.02]"
                  >
                    <span className="text-white/40">{k}</span>
                    <div className="flex items-center gap-1.5 text-white/65 font-medium">
                      <CheckCircle2 className="h-3.5 w-3.5 text-sirax-teal" strokeWidth={2.5} />
                      {v}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            {/* Floating mini-badge */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 1 }}
              className="absolute -left-4 -bottom-4 hidden md:flex items-center gap-2 px-3 py-2 rounded-lg bg-white text-sirax-navy shadow-xl border border-white/6"
            >
              <div className="h-7 w-7 rounded-md bg-sirax-teal/15 flex items-center justify-center">
                <Sparkles className="h-3.5 w-3.5 text-sirax-teal" />
              </div>
              <div className="text-[11px] font-semibold leading-tight">
                AI Report<br />
                <span className="text-white/45 font-normal">generado en 1.4s</span>
              </div>
            </motion.div>
          </div>
        </motion.div>

        {/* Scroll cue */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.4, duration: 0.8 }}
          className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/45 text-[10px] uppercase tracking-[0.3em] flex flex-col items-center gap-2"
        >
          <span>Scroll</span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ repeat: Infinity, duration: 1.6 }}
            className="h-6 w-px bg-gradient-to-b from-sirax-teal to-transparent"
          />
        </motion.div>
      </section>

      {/* Trust marquee */}
      <section className="bg-sirax-navy border-t border-white/5 py-6 overflow-hidden">
        <div className="flex items-center gap-3 mb-3 px-6 max-w-7xl mx-auto">
          <div className="text-[10px] uppercase tracking-[0.24em] text-white/45">
            Fuentes correlacionadas
          </div>
          <div className="flex-1 h-px bg-white/5" />
        </div>
        <div className="relative overflow-hidden sirax-no-scrollbar">
          <div className="flex w-max sirax-marquee gap-4">
            {[...coverageSources, ...coverageSources].map((s, i) => (
              <div
                key={i}
                className="px-4 py-2 rounded-md border border-white/10 bg-white/[0.03] text-xs font-mono font-medium text-white/40 whitespace-nowrap"
              >
                {s}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Modules */}
      <section id="modules" className="py-24 bg-white/[0.02] relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-sirax-teal/5 rounded-full blur-3xl" />
        <div className="relative max-w-7xl mx-auto px-6">
          <Reveal className="max-w-2xl mb-12">
            <div className="text-xs font-bold uppercase tracking-[0.2em] text-sirax-teal mb-3 flex items-center gap-2">
              <Layers className="h-3.5 w-3.5" />
              Arquitectura
            </div>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-sirax-navy mb-4">
              Una sola plataforma.<br />
              <span className="text-white/40">Diez módulos de inteligencia.</span>
            </h2>
            <p className="text-white/45 max-w-xl">
              Cada módulo opera de forma independiente o se correlaciona con los demás para
              construir una vista 360° del sujeto, con scoring estandarizado y reporte AI en
              español listo para auditoría.
            </p>
          </Reveal>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <LandingModule index={0} icon={IdCard} title="Identity Verification"
              desc="Validación de identidad oficial mexicana con algoritmo y registros."
              items={['CURP · dígito verificador', 'RFC PF · PM · Homoclave', 'RENAPO · SAT · IMSS']} />
            <LandingModule index={1} icon={ShieldCheck} title="Government Intelligence"
              desc="Consulta de fuentes gubernamentales y registros oficiales."
              items={['RENAPO · SAT · IMSS', 'RND (SSPC)', 'DOF · SCJN']} />
            <LandingModule index={2} icon={Scale} title="Compliance Intelligence"
              desc="Screening contra listas restrictivas globales y locales."
              items={['OFAC · ONU · Interpol', 'OpenSanctions · EU · UK', 'SAT 69-B · PEP México']} />
            <LandingModule index={3} icon={Globe2} title="Digital Identity Intelligence"
              desc="Verificación profunda de email, teléfono y aliases."
              items={['HIBP · Hunter · MX Records', 'Operador · spam · línea', 'Sherlock · Maigret']} />
            <LandingModule index={4} icon={Eye} title="Digital Footprint"
              desc="Descubrimiento de presencia en plataformas sociales."
              items={['LinkedIn · GitHub · X', 'Instagram · Reddit · TikTok', 'Discord · Telegram · Medium']} />
            <LandingModule index={5} icon={Network} title="Relationship Intelligence"
              desc="Knowledge graph con detección de patrones sospechosos."
              items={['Entity Resolution', 'Visualización interactiva', 'Detección de redes ocultas']} />
            <LandingModule index={6} icon={BarChart3} title="Risk Intelligence Engine"
              desc="Trust Score y Risk Score ponderados con recomendación."
              items={['Trust 0-100 · Risk 0-100', 'Identity Confidence', 'APPROVE · REVIEW · REJECT']} />
            <LandingModule index={7} icon={Brain} title="AI Investigation Engine"
              desc="Reportes automáticos en español con análisis multi-fuente."
              items={['Resumen ejecutivo', 'Análisis multi-fuente', 'Recomendación final']} />
            <LandingModule index={8} icon={Plug} title="API & Integrations"
              desc="REST API documentada para CRMs, ERPs, fintechs y bancos."
              items={['POST /verify · /curp · /rfc', 'POST /screening · /identity', 'Webhooks · SDKs']} />
          </div>
        </div>
      </section>

      {/* Coverage */}
      <section id="coverage" className="py-24 bg-white border-y border-white/8 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-12 gap-12 items-center">
            <Reveal className="lg:col-span-6" delay={0.05}>
              <div className="text-xs font-bold uppercase tracking-[0.2em] text-sirax-teal mb-3 flex items-center gap-2">
                <Radar className="h-3.5 w-3.5" />
                Cobertura
              </div>
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-sirax-navy mb-5 leading-tight">
                Sin reemplazar tus integraciones.<br />
                <span className="text-white/40">Las potencia.</span>
              </h2>
              <p className="text-white/45 mb-8 leading-relaxed max-w-xl">
                sirax se diseñó como capa unificadora: consume tus integraciones existentes
                y las correlaciona en una vista 360° del sujeto con scoring estandarizado y
                reporte AI generado automáticamente.
              </p>
              <div className="flex items-center gap-6">
                {[
                  { v: 18, suffix: '+', l: 'Fuentes activas' },
                  { v: 6, suffix: '', l: 'Países LATAM' },
                  { v: 5, suffix: 'M+', l: 'Registros screened' },
                ].map((s) => (
                  <div key={s.l}>
                    <div className="text-2xl font-bold text-sirax-navy">
                      <Counter to={s.v} suffix={s.suffix} />
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-white/40 mt-1">
                      {s.l}
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>

            <Reveal className="lg:col-span-6" delay={0.15}>
              <div className="grid grid-cols-3 gap-3">
                {coverageSources.slice(0, 12).map((s, i) => (
                  <motion.div
                    key={s}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.04, duration: 0.4 }}
                    whileHover={{ y: -2, borderColor: 'var(--sirax-teal)' }}
                    className="px-3 py-3 rounded-lg border border-white/8 bg-white/[0.02] text-xs font-mono font-medium text-white/70 text-center"
                  >
                    {s}
                  </motion.div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* API CTA with parallax */}
      <ApiCtaSection navigate={navigate} />

      {/* Footer */}
      <footer className="py-12 bg-sirax-navy text-white">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-12 gap-8 mb-8">
            <div className="md:col-span-5">
              <SiraxLogo size={32} variant="light" showTagline />
              <p className="text-sm text-white/40 mt-4 max-w-sm leading-relaxed">
                Identity & Risk Intelligence Platform. Verificación de identidad,
                background checks y risk intelligence para México y LATAM.
              </p>
              <div className="mt-4 text-xs text-sirax-teal font-semibold">
                Know More. Risk Less.
              </div>
            </div>
            <div className="md:col-span-2">
              <div className="text-[10px] uppercase tracking-[0.2em] text-white/45 mb-3">Plataforma</div>
              <ul className="space-y-2 text-sm text-white/40">
                <li><a href="#modules" className="hover:text-white transition-colors">Módulos</a></li>
                <li><a href="#coverage" className="hover:text-white transition-colors">Cobertura</a></li>
                <li><a href="#api" className="hover:text-white transition-colors">API</a></li>
                <li><button onClick={() => navigate('api-docs')} className="hover:text-white transition-colors">Documentación</button></li>
              </ul>
            </div>
            <div className="md:col-span-2">
              <div className="text-[10px] uppercase tracking-[0.2em] text-white/45 mb-3">Herramientas</div>
              <ul className="space-y-2 text-sm text-white/40">
                <li><button onClick={() => navigate('curp')} className="hover:text-white transition-colors">Validador CURP</button></li>
                <li><button onClick={() => navigate('rfc')} className="hover:text-white transition-colors">Validador RFC</button></li>
                <li><button onClick={() => navigate('sanctions')} className="hover:text-white transition-colors">Screening Sanciones</button></li>
              </ul>
            </div>
            <div className="md:col-span-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-white/45 mb-3">Synkdata</div>
              <ul className="space-y-2 text-sm text-white/40">
                <li className="flex items-center gap-2"><Building2 className="h-3.5 w-3.5" /> Ciudad de México</li>
                <li className="flex items-center gap-2"><Mail className="h-3.5 w-3.5" /> hello@synkdata.mx</li>
              </ul>
            </div>
          </div>
          <div className="pt-6 border-t border-white/5 flex flex-col md:flex-row gap-3 items-center justify-between text-xs text-white/45">
            <div className="flex items-center gap-2">
              <span>© 2026 sirax · a Synkdata product</span>
            </div>
            <div className="flex items-center gap-4">
              <span>Términos</span>
              <span>Privacidad</span>
              <span>Seguridad</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ==================== API CTA Section (separate so it can use its own scroll hook) ====================
function ApiCtaSection({ navigate }: { navigate: (v: View, data?: any) => void }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })
  const codeY = useTransform(scrollYProgress, [0, 1], [40, -40])
  const glowOpacity = useTransform(scrollYProgress, [0, 0.5, 1], [0, 0.7, 0])

  return (
    <section id="api" ref={ref} className="py-24 bg-sirax-navy text-white relative overflow-hidden">
      <motion.div
        style={{ opacity: glowOpacity }}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40rem] h-[40rem] bg-sirax-teal/10 rounded-full blur-3xl pointer-events-none"
      />
      <div className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center">
        <Reveal>
          <div className="h-12 w-12 rounded-xl bg-sirax-teal/15 flex items-center justify-center mb-5">
            <Lock className="h-6 w-6 text-sirax-teal" strokeWidth={1.75} />
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight mb-5 leading-tight">
            Una API.<br />
            <span className="sirax-gradient-text">Toda la inteligencia.</span>
          </h2>
          <p className="text-white/40 mb-8 max-w-md leading-relaxed">
            Diseñada para CRMs, fintechs, ERPs, bancos, marketplaces y plataformas de RH.
            Verifica identidad, evalúa riesgo y obtén un reporte AI en una sola llamada.
          </p>
          <div className="space-y-3 mb-8">
            {[
              ['POST', '/api/checks', 'Background check completo'],
              ['POST', '/api/identity/curp', 'Validación con dígito verificador'],
              ['POST', '/api/sanctions/screen', 'Screening fuzzy multi-lista'],
            ].map(([m, p, d]) => (
              <div key={p} className="flex items-center gap-3 text-xs font-mono">
                <span className="px-1.5 py-0.5 rounded bg-sirax-teal/15 text-sirax-teal font-bold">{m}</span>
                <span className="text-white">{p}</span>
                <span className="text-white/45">— {d}</span>
              </div>
            ))}
          </div>
          <motion.button
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => navigate('register')}
            className="inline-flex items-center gap-2 bg-sirax-teal text-sirax-navy px-5 py-3 rounded-md font-semibold text-sm hover:bg-sirax-teal-bright transition-colors"
          >
            Solicitar acceso <ArrowRight className="h-4 w-4" />
          </motion.button>
        </Reveal>

        <motion.div
          style={{ y: codeY }}
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="relative"
        >
          <div className="rounded-xl border border-white/10 bg-sirax-navy-soft/80 p-5 font-mono text-xs leading-6 text-white/55 backdrop-blur shadow-2xl">
            <div className="flex items-center gap-2 mb-4">
              <div className="h-2.5 w-2.5 rounded-full bg-rose-400/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-400/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-sirax-teal/60" />
              <div className="ml-2 text-[10px] text-white/45">background_check.sh</div>
            </div>
            <div className="text-white/45 mb-1"># Background check completo</div>
            <div><span className="text-rose-400">POST</span> /api/checks</div>
            <div className="text-white/45 mt-3">{'{'}</div>
            <div className="pl-3">
              <span className="text-sky-400">{'"full_name"'}</span>: <span className="text-sirax-teal-bright">{'"Juan Pérez García"'}</span>,<br />
              <span className="text-sky-400">{'"curp"'}</span>: <span className="text-sirax-teal-bright">{'"PEGJ800101HDFRRN09"'}</span>,<br />
              <span className="text-sky-400">{'"rfc"'}</span>: <span className="text-sirax-teal-bright">{'"PEGJ800101AB1"'}</span>,<br />
              <span className="text-sky-400">{'"email"'}</span>: <span className="text-sirax-teal-bright">{'"juan@empresa.mx"'}</span>,<br />
              <span className="text-sky-400">{'"include_ai_report"'}</span>: <span className="text-amber-400">true</span>
            </div>
            <div className="text-white/45">{'}'}</div>
            <div className="mt-3 pt-3 border-t border-white/5">
              <div className="text-sirax-teal">
                trust_score: 92 · risk_level: BAJO · recommendation: APPROVE
              </div>
              <div className="text-white/45 mt-1">
                ai_report: ✓ generado en 1.4s · 8 fuentes correlacionadas
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ==================== Login ====================
function LoginView() {
  const { login } = useAuth()
  const { navigate } = useRouter()
  const { toast } = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    const data = await API.post('/api/auth/login', { email, password })
    if (data.token) {
      login(data.token, data.user)
      navigate('dashboard')
    } else {
      toast({ title: 'Error', description: data.error || 'Credenciales inválidas', variant: 'destructive' })
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex lg:w-1/2 bg-sirax-navy text-white flex-col justify-center items-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 sirax-grid opacity-50" />
        <ParticleField />
        <div className="absolute -top-32 -right-32 w-96 h-96 bg-sirax-teal/15 rounded-full blur-3xl" />
        <div className="relative">
          <SiraxLogo size={56} variant="light" showTagline />
          <div className="mt-8 max-w-sm">
            <h1 className="text-3xl font-extrabold tracking-tight mb-3">
              Know More.<br />
              <span className="sirax-gradient-text">Risk Less.</span>
            </h1>
            <p className="text-white/40 leading-relaxed">
              Identity & Risk Intelligence Platform. Verificación de identidad,
              background checks y risk intelligence para México y LATAM.
            </p>
          </div>
          <div className="mt-8 p-4 rounded-lg border border-white/10 bg-white/[0.03] text-xs font-mono backdrop-blur">
            <div className="text-white/45 mb-2">Demo credentials:</div>
            <div>Admin: <span className="text-sirax-teal">admin@synkdata.mx</span></div>
            <div>Analyst: <span className="text-sirax-teal">analyst@synkdata.mx</span></div>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <button onClick={() => navigate('landing')} className="flex items-center gap-2 mb-8 text-white/45 hover:text-white text-sm">
            <ChevronLeft className="h-4 w-4" /> Volver al inicio
          </button>
          <div className="mb-8 lg:hidden">
            <SiraxLogo size={36} variant="dark" />
          </div>
          <h2 className="text-3xl font-bold text-sirax-navy mb-2">Iniciar sesión</h2>
          <p className="text-white/45 mb-8">Accede a la consola de Identity Intelligence.</p>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
                placeholder="tu@email.com" />
            </div>
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
                placeholder="••••••••" />
            </div>
            <button type="submit" disabled={loading}
              className="w-full bg-sirax-navy text-white py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft transition-colors disabled:opacity-50">
              {loading ? 'Verificando...' : 'Iniciar sesión'}
            </button>
          </form>
          <p className="text-sm text-white/45 mt-6 text-center">
            ¿No tienes cuenta? <button onClick={() => navigate('register')} className="text-sirax-teal font-semibold hover:underline">Crear cuenta</button>
          </p>
        </div>
      </div>
    </div>
  )
}

// ==================== Register ====================
function RegisterView() {
  const { login } = useAuth()
  const { navigate } = useRouter()
  const { toast } = useToast()
  const [form, setForm] = useState({ email: '', password: '', fullName: '', organization: '' })
  const [loading, setLoading] = useState(false)

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    const data = await API.post('/api/auth/register', { ...form, role: 'analyst' })
    if (data.token) {
      login(data.token, data.user)
      navigate('dashboard')
    } else {
      toast({ title: 'Error', description: data.error || 'No se pudo crear la cuenta', variant: 'destructive' })
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex lg:w-1/2 bg-sirax-navy text-white flex-col justify-center items-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 sirax-grid opacity-50" />
        <ParticleField />
        <div className="absolute -bottom-32 -left-32 w-96 h-96 bg-sirax-teal/15 rounded-full blur-3xl" />
        <div className="relative">
          <SiraxLogo size={56} variant="light" showTagline />
          <div className="mt-8 max-w-sm">
            <h1 className="text-3xl font-extrabold tracking-tight mb-3">
              Únete a sirax.
            </h1>
            <p className="text-white/40 leading-relaxed">
              Accede a la plataforma de Identity & Risk Intelligence más completa
              para México y Latinoamérica.
            </p>
            <div className="mt-6 text-sm text-sirax-teal font-semibold">
              Know More. Risk Less.
            </div>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-md">
          <button onClick={() => navigate('landing')} className="flex items-center gap-2 mb-8 text-white/45 hover:text-white text-sm">
            <ChevronLeft className="h-4 w-4" /> Volver al inicio
          </button>
          <div className="mb-8 lg:hidden">
            <SiraxLogo size={36} variant="dark" />
          </div>
          <h2 className="text-3xl font-bold text-sirax-navy mb-2">Crear cuenta</h2>
          <p className="text-white/45 mb-8">Regístrate para acceder a la plataforma.</p>
          <form onSubmit={handleRegister} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Nombre completo</label>
              <input type="text" value={form.fullName} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))} required
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5" />
            </div>
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Email</label>
              <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5" />
            </div>
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Organización</label>
              <input type="text" value={form.organization} onChange={e => setForm(f => ({ ...f, organization: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5" />
            </div>
            <div>
              <label className="text-sm font-medium text-white/70 mb-1 block">Password</label>
              <input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required
                className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5" />
            </div>
            <button type="submit" disabled={loading}
              className="w-full bg-sirax-navy text-white py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft transition-colors disabled:opacity-50">
              {loading ? 'Creando cuenta...' : 'Crear cuenta'}
            </button>
          </form>
          <p className="text-sm text-white/45 mt-6 text-center">
            ¿Ya tienes cuenta? <button onClick={() => navigate('login')} className="text-sirax-teal font-semibold hover:underline">Iniciar sesión</button>
          </p>
        </div>
      </div>
    </div>
  )
}

// ==================== Dashboard Layout ====================
function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const { navigate, view } = useRouter()
  const [mobileOpen, setMobileOpen] = useState(false)

  const navItems: { key: View; label: string; icon: any }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { key: 'new-check', label: 'Nuevo Check', icon: Plus },
    { key: 'history', label: 'Historial', icon: Search },
    { key: 'curp', label: 'Validador CURP', icon: IdCard },
    { key: 'rfc', label: 'Validador RFC', icon: Hash },
    { key: 'sanctions', label: 'Screening Sanciones', icon: Scale },
    { key: 'api-docs', label: 'API & Docs', icon: Plug },
  ]

  return (
    <div className="min-h-screen flex" style={{backgroundColor:"oklch(0.07 0.012 250)"}}>
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-sirax-navy text-white transform transition-transform lg:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="h-16 flex items-center px-5 border-b border-white/5">
          <SiraxLogo size={28} variant="light" />
        </div>
        <nav className="p-4 space-y-1">
          {navItems.map(item => {
            const active = view === item.key
            return (
              <button key={item.key} onClick={() => { navigate(item.key); setMobileOpen(false) }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  active ? 'bg-sirax-teal/15 text-sirax-teal' : 'text-white/40 hover:bg-white/5 hover:text-white'
                }`}>
                <item.icon className="h-4 w-4" strokeWidth={1.75} />
                {item.label}
                {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-sirax-teal" />}
              </button>
            )
          })}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-white/5">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-8 w-8 bg-sirax-teal/20 rounded-full flex items-center justify-center">
              <User className="h-4 w-4 text-sirax-teal" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-white truncate">{user?.full_name}</div>
              <div className="text-[10px] uppercase tracking-wider text-white/45">{user?.role}</div>
            </div>
          </div>
          <button onClick={() => { logout(); navigate('landing') }}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-white/40 hover:bg-white/5 hover:text-white transition-colors">
            <LogOut className="h-4 w-4" /> Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 lg:ml-64">
        <header className="h-16 flex items-center justify-between px-6 lg:px-8 border-b border-white/8" style={{backgroundColor:"oklch(0.09 0.013 250)"}}>
          <button onClick={() => setMobileOpen(true)} className="lg:hidden">
            <Menu className="h-5 w-5 text-white/60" />
          </button>
          <div className="flex items-center gap-3">
            <div className="text-xs font-bold uppercase tracking-[0.2em] text-white/40">
              Identity & Risk Intelligence
            </div>
            <span className="hidden md:inline px-2 py-0.5 rounded text-[10px] font-semibold bg-sirax-teal/10 text-sirax-teal uppercase tracking-wider">
              a Synkdata product
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('new-check')}
              className="hidden sm:inline-flex items-center gap-2 bg-sirax-teal/15 border border-sirax-teal/30 text-sirax-teal px-3 py-1.5 rounded-md text-xs font-semibold hover:bg-sirax-teal/25 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Nuevo Check
            </button>
          </div>
        </header>
        <main>{children}</main>
      </div>

      {/* Mobile overlay */}
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} />}
    </div>
  )
}

// ==================== Stat Card ====================
function StatCard({ icon: Icon, label, value, sub, accent }: { icon: any; label: string; value: any; sub?: string; accent?: string }) {
  return (
    <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
      <div className={`h-9 w-9 flex items-center justify-center rounded-md mb-3 ${accent || 'bg-sirax-navy text-white'}`}>
        <Icon className="h-4 w-4" strokeWidth={1.75} />
      </div>
      <div className="text-3xl font-extrabold tracking-tighter text-white">{value}</div>
      <div className="text-xs uppercase tracking-wider text-white/50 font-semibold mt-1">{label}</div>
      {sub && <div className="text-xs text-white/35 mt-2">{sub}</div>}
    </div>
  )
}

// ==================== Dashboard View ====================
function DashboardView() {
  const { user, token } = useAuth()
  const { navigate } = useRouter()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      API.get('/api/analytics/dashboard', token).then(d => { setData(d); setLoading(false) })
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- estado inicial de carga cuando no hay token
      setLoading(false)
    }
  }, [token])

  if (loading) return <div className="p-8"><div className="animate-pulse space-y-4"><div className="h-8 bg-white/8 rounded w-64" /><div className="grid grid-cols-4 gap-5">{[1,2,3,4].map(i => <div key={i} className="h-32 bg-white/8 rounded-lg" />)}</div></div></div>

  const riskData = Object.entries(data?.risk_distribution || {}).map(([level, count]: any) => ({ level, count, fill: RISK_COLORS[level] }))
  const recData = Object.entries(data?.recommendation_distribution || {}).map(([rec, count]: any) => ({ name: REC_LABEL[rec] || rec, value: count, fill: REC_COLORS[rec] }))

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5 flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            Dashboard ejecutivo
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tighter text-sirax-navy">
            Bienvenido, {user?.full_name?.split(' ')[0]}
          </h1>
          <p className="text-sm text-white/50 mt-1">Identity Intelligence en tiempo real</p>
        </div>
        <button onClick={() => navigate('new-check')}
          className="inline-flex items-center gap-2 bg-sirax-teal text-sirax-navy px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-teal-bright transition-colors">
          <FileSearch className="h-4 w-4" /> Nuevo Background Check <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard icon={FileSearch} label="Checks procesados" value={data?.total_checks ?? 0} sub="Histórico total" accent="bg-sirax-navy text-white" />
        <StatCard icon={CheckCircle2} label="Trust Score promedio" value={data?.average_trust_score ?? 0} sub="Promedio" accent="bg-sirax-teal/15 text-sirax-teal" />
        <StatCard icon={ShieldAlert} label="Risk Score promedio" value={data?.average_risk_score ?? 0} sub="Promedio" accent="bg-amber-100 text-amber-700" />
        <StatCard icon={Scale} label="Coincidencias sanciones" value={data?.sanctions_matches ?? 0} sub={`PEP: ${data?.pep_matches ?? 0}`} accent="bg-rose-100 text-rose-700" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">Distribución</div>
              <h3 className="font-bold text-white">Niveles de riesgo</h3>
            </div>
            <TrendingUp className="h-4 w-4 text-white/40" />
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={riskData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis dataKey="level" stroke="rgba(255,255,255,0.4)" fontSize={11} />
              <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={{ background: 'rgba(8,10,15,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: 'white', fontSize: 12 }} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {riskData.map((entry, index) => <Cell key={index} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="mb-4">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">Recomendaciones</div>
            <h3 className="font-bold text-white">Veredicto</h3>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={recData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2}>
                {recData.map((entry, index) => <Cell key={index} fill={entry.fill} />)}
              </Pie>
              <Tooltip contentStyle={{ background: 'rgba(8,10,15,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: 'white', fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="mb-4">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">Tendencia</div>
            <h3 className="font-bold text-white">Checks últimos 14 días</h3>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data?.trend_14_days || []}>
              <defs>
                <linearGradient id="gradChecks" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis dataKey="date" stroke="rgba(255,255,255,0.4)" fontSize={10} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: 'rgba(8,10,15,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: 'white', fontSize: 12 }} labelStyle={{ color: 'rgba(255,255,255,0.7)' }} />
              <Area type="monotone" dataKey="count" stroke="#22d3ee" strokeWidth={2} fill="url(#gradChecks)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <h3 className="font-bold text-white mb-1">Checks recientes</h3>
          <div className="text-[10px] uppercase tracking-wider text-white/40 mb-3">Últimas verificaciones</div>
          <div className="space-y-2 max-h-[260px] overflow-y-auto">
            {(data?.recent_checks || []).map((c: any) => (
              <button key={c.id} onClick={() => navigate('check-results', { checkId: c.id })}
                className="flex items-center gap-3 p-2.5 w-full text-left rounded-md hover:bg-white/5 transition-colors">
                <div className={`w-1 h-9 rounded-full ${c.risk_level === 'BAJO' ? 'bg-sirax-teal' : c.risk_level === 'MEDIO' ? 'bg-amber-500' : c.risk_level === 'ALTO' ? 'bg-rose-500' : 'bg-rose-700'}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-white truncate">{c.subject?.full_name}</div>
                  <div className="text-[10px] text-white/40 font-mono">{(c.created_at || '').slice(0, 16).replace('T', ' ')}</div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="text-xs font-bold text-white">{c.trust_score}</div>
                  {c.recommendation === 'APPROVE' ? <CheckCircle2 className="h-4 w-4 text-sirax-teal" /> :
                   c.recommendation === 'REVIEW' ? <Eye className="h-4 w-4 text-amber-500" /> :
                   <XCircle className="h-4 w-4 text-rose-500" />}
                </div>
              </button>
            ))}
            {(!data?.recent_checks || data.recent_checks.length === 0) && (
              <div className="text-sm text-white/40 text-center py-6 flex flex-col items-center gap-2">
                <AlertTriangle className="h-5 w-5" />
                <span>Aún no hay checks. Crea el primero.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ==================== New Check Wizard ====================
function NewCheckView() {
  const token = useToken()
  const { navigate } = useRouter()
  const { toast } = useToast()
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    full_name: '', curp: '', rfc: '', email: '', phone: '', username: '', address: '',
    include_government: true, include_sanctions: true, include_digital: true,
    include_relationship: true, include_ai_report: true,
  })

  const steps = ['Personal', 'Identidad', 'Digital', 'Módulos']
  const stepIcons = [User, IdCard, Globe2, Zap]

  const handleSubmit = async () => {
    if (!form.full_name.trim()) { toast({ title: 'Error', description: 'Nombre completo es requerido', variant: 'destructive' }); return }
    setLoading(true)
    const data = await API.post('/api/checks', form, token)
    if (data.id) {
      toast({ title: 'Check completado', description: `Trust: ${data.trust_score} | Risk: ${data.risk_score} | ${data.recommendation}` })
      navigate('check-results', { checkId: data.id, checkData: data })
    } else {
      toast({ title: 'Error', description: data.error || 'No se pudo crear el check', variant: 'destructive' })
    }
    setLoading(false)
  }

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Background Check</div>
        <h1 className="text-3xl font-extrabold tracking-tighter text-white">Nueva verificación</h1>
        <p className="text-sm text-white/50 mt-1">Completa los datos del sujeto para el análisis de identidad.</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {steps.map((s, i) => (
          <React.Fragment key={s}>
            <button onClick={() => i < step && setStep(i)}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs font-semibold transition-colors ${
                i === step ? 'bg-sirax-teal/20 text-sirax-teal border border-sirax-teal/30' : i < step ? 'bg-sirax-teal/10 text-sirax-teal cursor-pointer' : 'bg-white/5 text-white/30'
              }`}>
              {React.createElement(stepIcons[i], { className: 'h-3.5 w-3.5' })}
              {s}
            </button>
            {i < steps.length - 1 && <div className="w-8 h-px bg-white/8" />}
          </React.Fragment>
        ))}
      </div>

      {/* Step 0: Personal */}
      {step === 0 && (
        <div className="space-y-4 rounded-2xl p-6 border border-white/8 bg-white/[0.025] sirax-card-glow">
          <h2 className="font-bold text-white text-lg mb-4">Datos personales</h2>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">Nombre completo *</label>
            <input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="Juan Pérez García" />
          </div>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">Dirección</label>
            <input value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="Ciudad de México, CDMX" />
          </div>
        </div>
      )}

      {/* Step 1: Identity */}
      {step === 1 && (
        <div className="space-y-4 rounded-2xl p-6 border border-white/8 bg-white/[0.025] sirax-card-glow">
          <h2 className="font-bold text-white text-lg mb-4">Datos de identidad</h2>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">CURP</label>
            <input value={form.curp} onChange={e => setForm(f => ({ ...f, curp: e.target.value.toUpperCase() }))} maxLength={18}
              className="w-full px-3 py-2 rounded-md text-sm font-mono text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="PEGJ800101HDFRRN09" />
            <p className="text-[10px] text-white/30 mt-1">18 caracteres · Algoritmo de verificación oficial</p>
          </div>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">RFC</label>
            <input value={form.rfc} onChange={e => setForm(f => ({ ...f, rfc: e.target.value.toUpperCase() }))} maxLength={13}
              className="w-full px-3 py-2 rounded-md text-sm font-mono text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="PEGJ800101AB1" />
            <p className="text-[10px] text-white/30 mt-1">12 (moral) o 13 (física) caracteres</p>
          </div>
        </div>
      )}

      {/* Step 2: Digital */}
      {step === 2 && (
        <div className="space-y-4 rounded-2xl p-6 border border-white/8 bg-white/[0.025] sirax-card-glow">
          <h2 className="font-bold text-white text-lg mb-4">Identidad digital</h2>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">Email</label>
            <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="juan@empresa.mx" />
          </div>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">Teléfono</label>
            <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="+52 55 1234 5678" />
          </div>
          <div>
            <label className="text-sm font-medium text-white/70 mb-1 block">Username / Alias</label>
            <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
              placeholder="snupdrack" />
          </div>
        </div>
      )}

      {/* Step 3: Modules */}
      {step === 3 && (
        <div className="space-y-4 rounded-2xl p-6 border border-white/8 bg-white/[0.025] sirax-card-glow">
          <h2 className="font-bold text-white text-lg mb-4">Módulos de análisis</h2>
          <p className="text-sm text-white/50 mb-4">Selecciona qué módulos incluir en la verificación.</p>
          {[
            { key: 'include_government', label: 'Government Intelligence', desc: 'RENAPO, SAT, IMSS, RND', icon: ShieldCheck },
            { key: 'include_sanctions', label: 'Compliance Intelligence', desc: 'OFAC, ONU, PEP, SAT 69-B, Interpol', icon: Scale },
            { key: 'include_digital', label: 'Digital Identity & Footprint', desc: 'Email, teléfono, username, redes sociales', icon: Globe2 },
            { key: 'include_relationship', label: 'Relationship Intelligence', desc: 'Knowledge graph y detección de patrones', icon: Network },
            { key: 'include_ai_report', label: 'AI Investigation Report', desc: 'Reporte automático de investigación', icon: Brain },
          ].map(m => (
            <label key={m.key} className={`flex items-center gap-4 p-4 rounded-md border cursor-pointer transition-colors ${
              (form as any)[m.key] ? 'border-sirax-teal bg-sirax-teal/10' : 'border-white/10 bg-white/[0.025]'
            }`}>
              <input type="checkbox" checked={(form as any)[m.key]}
                onChange={e => setForm(f => ({ ...f, [m.key]: e.target.checked }))}
                className="h-4 w-4 rounded border-slate-300 accent-[#00d1a0]" />
              <m.icon className="h-5 w-5 text-white/60" strokeWidth={1.75} />
              <div>
                <div className="text-sm font-semibold text-white">{m.label}</div>
                <div className="text-xs text-white/40">{m.desc}</div>
              </div>
            </label>
          ))}
        </div>
      )}

      {/* Navigation buttons */}
      <div className="flex items-center justify-between mt-6">
        <button onClick={() => step > 0 ? setStep(step - 1) : navigate('dashboard')}
          className="flex items-center gap-2 text-sm text-white/50 hover:text-white transition-colors">
          <ChevronLeft className="h-4 w-4" /> {step > 0 ? 'Anterior' : 'Cancelar'}
        </button>
        {step < 3 ? (
          <button onClick={() => setStep(step + 1)} disabled={!form.full_name.trim()}
            className="flex items-center gap-2 bg-sirax-navy text-white px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft disabled:opacity-50">
            Siguiente <ChevronRight className="h-4 w-4" />
          </button>
        ) : (
          <button onClick={handleSubmit} disabled={loading}
            className="flex items-center gap-2 bg-sirax-teal text-sirax-navy px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-teal-bright disabled:opacity-50">
            {loading ? (
              <><RefreshCw className="h-4 w-4 animate-spin" /> Procesando...</>
            ) : (
              <><Zap className="h-4 w-4" /> Ejecutar verificación</>
            )}
          </button>
        )}
      </div>
    </div>
  )
}

// ==================== Score Gauge (SVG animado — estilo siraxlanding) ====================
function ScoreGauge({ value, label, color }: { value: number; label: string; color: string }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [display, setDisplay] = useState(0)
  const [animated, setAnimated] = useState(false)

  useEffect(() => {
    if (!ref.current) return
    const obs = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting && !animated) setAnimated(true) },
      { threshold: 0.4 }
    )
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [animated])

  useEffect(() => {
    if (!animated) return
    let raf = 0
    const start = performance.now()
    const dur = 1400
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplay(Math.round(value * eased))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [animated, value])

  const radius = 70
  const circ = 2 * Math.PI * radius
  const offset = circ - (display / 100) * circ

  return (
    <div ref={ref} className="text-center">
      <div className="relative inline-flex items-center justify-center">
        <svg viewBox="0 0 180 180" className="w-36 h-36 -rotate-90">
          <circle cx="90" cy="90" r={radius} stroke="rgba(255,255,255,0.06)" strokeWidth="10" fill="none" />
          <motion.circle
            cx="90" cy="90" r={radius}
            stroke={color} strokeWidth="10" fill="none" strokeLinecap="round"
            strokeDasharray={circ}
            initial={{ strokeDashoffset: circ }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
            style={{ filter: `drop-shadow(0 0 6px ${color}55)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color }}>{display}</span>
          <span className="text-[10px] text-white/40 uppercase tracking-wider">/ 100</span>
        </div>
      </div>
      <div className="text-[10px] uppercase tracking-wider text-white/40 mt-1">{label}</div>
    </div>
  )
}

// ==================== Check Results ====================
function CheckResultsView() {
  const token = useToken()
  const { navigate } = useRouter()
  const { viewData } = useRouter()
  const [check, setCheck] = useState<any>(viewData?.checkData || null)
  const [loading, setLoading] = useState(!check)

  useEffect(() => {
    if (!check && viewData?.checkId && token) {
      API.get(`/api/checks/${viewData.checkId}`, token).then(d => { setCheck(d); setLoading(false) })
    }
  }, [check, viewData, token])

  const [pdfLoading, setPdfLoading] = useState(false)
  const { toast } = useToast()

  if (loading) return <div className="p-8 animate-pulse space-y-4"><div className="h-8 bg-white/8 rounded w-96" /><div className="h-64 bg-white/8 rounded-lg" /></div>
  if (!check) return <div className="p-8"><p className="text-white/45">No se encontró el check.</p></div>

  const riskColor = RISK_COLORS[check.risk_level] || '#64748b'

  const handleDownloadPDF = async () => {
    setPdfLoading(true)
    try {
      await generateCheckPDF(check)
      toast({ title: 'PDF generado', description: 'El reporte se descargó correctamente.' })
    } catch (e) {
      console.error(e)
      toast({ title: 'Error al generar PDF', description: 'Intenta de nuevo.', variant: 'destructive' })
    } finally {
      setPdfLoading(false)
    }
  }

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <button onClick={() => navigate('history')} className="text-sm text-white/45 hover:text-white flex items-center gap-1 mb-2">
            <ChevronLeft className="h-4 w-4" /> Historial
          </button>
          <h1 className="text-3xl font-extrabold tracking-tighter text-white">{check.subject?.full_name}</h1>
          <div className="flex items-center gap-3 mt-2">
            <div className="px-2 py-0.5 rounded text-xs font-bold text-white" style={{ backgroundColor: riskColor }}>{check.risk_level}</div>
            <div className="text-sm text-white/45">Recomendación: {check.recommendation}</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-white/40 font-mono">{check.created_at?.slice(0, 19).replace('T', ' ')}</div>
          <motion.button
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleDownloadPDF}
            disabled={pdfLoading}
            className="inline-flex items-center gap-2 bg-sirax-teal text-sirax-navy px-4 py-2 rounded-lg font-semibold text-sm hover:bg-sirax-teal-bright transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {pdfLoading
              ? <><RefreshCw className="h-4 w-4 animate-spin" /> Generando PDF…</>
              : <><Download className="h-4 w-4" /> Descargar Reporte PDF</>
            }
          </motion.button>
        </div>
      </div>

      {/* Scores */}
      <div className="grid grid-cols-3 gap-4 rounded-2xl p-6 border border-white/8 bg-white/[0.025] sirax-card-glow">
        <ScoreGauge value={check.trust_score} label="Trust Score" color="#00d1a0" />
        <ScoreGauge value={check.risk_score} label="Risk Score" color={riskColor} />
        <ScoreGauge value={check.identity_confidence} label="Confianza" color="#6366f1" />
      </div>

      {/* Flags */}
      {check.flags?.length > 0 && (
        <div className="p-4 rounded-xl border border-rose-500/20 bg-rose-500/10">
          <div className="flex items-center gap-2 text-rose-400 font-semibold text-sm mb-2"><AlertTriangle className="h-4 w-4" /> Alertas</div>
          {check.flags.map((f: string, i: number) => (
            <div key={i} className="text-sm text-rose-400 flex items-center gap-2"><Flag className="h-3 w-3" />{f}</div>
          ))}
        </div>
      )}

      {/* Module results in tabs-like layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* CURP */}
        {check.curp_validation && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <IdCard className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">CURP</h3>
              {check.curp_validation.is_valid ?
                <CheckCircle2 className="h-4 w-4 text-sirax-teal" /> :
                <XCircle className="h-4 w-4 text-rose-500" />}
            </div>
            <div className="text-sm font-mono bg-white/[0.02] p-3 rounded mb-3">{check.curp_validation.curp}</div>
            <div className="text-sm text-white/60">{check.curp_validation.message}</div>
            {check.curp_validation.components && (
              <div className="mt-3 space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-white/40">Fecha nacimiento</span><span className="text-sirax-navy font-medium">{check.curp_validation.components.birth_date}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Sexo</span><span className="text-sirax-navy font-medium">{check.curp_validation.components.sex}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Estado</span><span className="text-sirax-navy font-medium">{check.curp_validation.components.state}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Dígito verificador</span><span className="text-sirax-navy font-medium">{check.curp_validation.check_digit_valid ? '✓ Válido' : '✗ Inválido'}</span></div>
              </div>
            )}
          </div>
        )}

        {/* RFC */}
        {check.rfc_validation && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <Hash className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">RFC</h3>
              {check.rfc_validation.is_valid ?
                <CheckCircle2 className="h-4 w-4 text-sirax-teal" /> :
                <XCircle className="h-4 w-4 text-rose-500" />}
            </div>
            <div className="text-sm font-mono bg-white/[0.02] p-3 rounded mb-3">{check.rfc_validation.rfc}</div>
            <div className="text-sm text-white/60">{check.rfc_validation.message}</div>
            {check.rfc_validation.components && (
              <div className="mt-3 space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-white/40">Tipo</span><span className="text-sirax-navy font-medium">{check.rfc_validation.type === 'fisica' ? 'Persona Física' : 'Persona Moral'}</span></div>
                <div className="flex justify-between"><span className="text-white/40">SAT Status</span><span className={`font-medium ${check.rfc_validation.sat_status === 'ACTIVO' ? 'text-sirax-teal' : 'text-rose-600'}`}>{check.rfc_validation.sat_status}</span></div>
                <div className="flex justify-between"><span className="text-white/40">Régimen</span><span className="text-sirax-navy font-medium">{check.rfc_validation.regimen_fiscal}</span></div>
              </div>
            )}
          </div>
        )}

        {/* Government */}
        {check.government && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">Government Intelligence</h3>
            </div>
            <div className="space-y-3">
              {check.government.renapo && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">RENAPO</div>
                  <div className="text-sm">{check.government.renapo.found ? <span className="text-sirax-teal font-medium">Registro vigente</span> : <span className="text-white/45">No encontrado</span>}</div>
                </div>
              )}
              {check.government.sat && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">SAT</div>
                  <div className="text-sm">Status: <span className={check.government.sat.status === 'ACTIVO' ? 'text-sirax-teal' : 'text-rose-600'}>{check.government.sat.status}</span></div>
                </div>
              )}
              {check.government.rnd && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">RND (Detenciones)</div>
                  <div className="text-sm">{check.government.rnd.sin_resultados ? <span className="text-sirax-teal">Sin registros</span> : <span className="text-rose-600 font-medium">Registro encontrado</span>}</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Sanctions */}
        {check.sanctions && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <Scale className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">Compliance Intelligence</h3>
              {check.sanctions.is_sanctioned ?
                <XCircle className="h-4 w-4 text-rose-500" /> :
                check.sanctions.is_pep ? <AlertTriangle className="h-4 w-4 text-amber-500" /> :
                <CheckCircle2 className="h-4 w-4 text-sirax-teal" />}
            </div>
            <div className="text-sm mb-3">
              {check.sanctions.is_sanctioned ? <span className="text-rose-600 font-semibold">Match en listas de sanciones</span> :
               check.sanctions.is_pep ? <span className="text-amber-600 font-semibold">Persona Expuesta Políticamente (PEP)</span> :
               <span className="text-sirax-teal font-semibold">Sin coincidencias en listas restringidas</span>}
            </div>
            {check.sanctions.matches?.length > 0 && (
              <div className="space-y-2">
                {check.sanctions.matches.map((m: any, i: number) => (
                  <div key={i} className="p-2 rounded border border-white/8 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sirax-navy">{m.matched_name}</span>
                      <span className="text-white/40">{m.score}%</span>
                    </div>
                    <div className="text-white/45">{m.list_name} · {m.type} · {m.country}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="text-[10px] text-white/40 mt-3">{check.sanctions.lists_checked?.length || 0} listas consultadas · {check.sanctions.total_records_screened} registros</div>
          </div>
        )}

        {/* Digital Identity */}
        {check.digital_identity && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <Globe2 className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">Digital Identity Intelligence</h3>
            </div>
            <div className="space-y-3">
              {check.digital_identity.email && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">Email</div>
                  <div className="text-sm font-mono">{check.digital_identity.email.email}</div>
                  <div className="text-xs text-white/45 mt-1">
                    {check.digital_identity.email.is_disposable ? <span className="text-rose-600 font-semibold">DESECHEABLE</span> :
                     check.digital_identity.email.is_corporate_business ? <span className="text-sirax-teal">Corporativo</span> : 'Personal'}
                    {' · '}{check.digital_identity.email.breach_count} brechas
                  </div>
                </div>
              )}
              {check.digital_identity.phone && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">Teléfono</div>
                  <div className="text-sm">{check.digital_identity.phone.carrier} · {check.digital_identity.phone.line_type}</div>
                  {check.digital_identity.phone.is_spam_reported && <div className="text-xs text-rose-600 font-semibold">Reportado como spam</div>}
                </div>
              )}
              {check.digital_identity.username?.found && (
                <div className="p-3 bg-white/[0.02] rounded">
                  <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-1">Username: {check.digital_identity.username.username}</div>
                  <div className="text-sm">{check.digital_identity.username.profile_count} perfiles encontrados</div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {check.digital_identity.username.profiles?.slice(0, 6).map((p: any) => (
                      <span key={p.platform} className="px-2 py-0.5 bg-white border border-white/8 rounded text-[10px] font-mono text-white/60">{p.platform}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Digital Footprint */}
        {check.digital_footprint && (
          <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
            <div className="flex items-center gap-2 mb-3">
              <Eye className="h-4 w-4 text-white/60" strokeWidth={1.75} />
              <h3 className="font-bold text-white">Digital Footprint</h3>
            </div>
            <div className="flex items-center gap-4 mb-4">
              <div className="text-4xl font-extrabold tracking-tighter text-sirax-navy">{check.digital_footprint.presence_score}</div>
              <div>
                <div className="text-xs uppercase tracking-wider text-white/40">Presencia digital</div>
                <div className="text-sm text-white/60">{check.digital_footprint.social_profiles_count} social · {check.digital_footprint.developer_profiles_count} dev</div>
              </div>
            </div>
            {check.digital_footprint.professional_presence && (
              <div className="text-xs text-sirax-teal font-semibold flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> Presencia profesional detectada</div>
            )}
          </div>
        )}
      </div>

      {/* Relationship Graph (simplified visual) */}
      {check.relationship_graph && (
        <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="flex items-center gap-2 mb-4">
            <Network className="h-4 w-4 text-white/60" strokeWidth={1.75} />
            <h3 className="font-bold text-white">Relationship Intelligence</h3>
            <span className="text-xs text-white/40 ml-2">{check.relationship_graph.analysis?.total_nodes} nodos · {check.relationship_graph.analysis?.total_edges} conexiones</span>
          </div>
          {check.relationship_graph.analysis?.suspicious_patterns?.length > 0 && (
            <div className="p-3 rounded border border-rose-200 bg-rose-50 mb-4">
              {check.relationship_graph.analysis.suspicious_patterns.map((p: any, i: number) => (
                <div key={i} className="text-sm text-rose-700 flex items-center gap-2"><AlertTriangle className="h-4 w-4" />{p.description}</div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {check.relationship_graph.graph?.nodes?.map((n: any) => (
              <div key={n.data.id}
                className={`px-3 py-2 rounded-md border text-xs font-medium ${
                  n.data.type === 'Person' ? 'bg-white/5 border-slate-300 text-sirax-navy' :
                  n.data.type === 'Email' ? 'bg-sky-50 border-sky-200 text-sky-700' :
                  n.data.type === 'Phone' ? 'bg-cyan-50 border-cyan-200 text-cyan-700' :
                  n.data.type === 'Curp' ? 'bg-purple-50 border-purple-200 text-purple-700' :
                  n.data.type === 'Rfc' ? 'bg-violet-50 border-violet-200 text-violet-700' :
                  n.data.type === 'SanctionMatch' ? 'bg-rose-50 border-rose-200 text-rose-700' :
                  n.data.type === 'SocialProfile' ? 'bg-gray-50 border-gray-200 text-gray-700' :
                  'bg-white/[0.02] border-white/8 text-white/60'
                }`}>
                {n.data.label}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Score Breakdown */}
      {check.breakdown && (
        <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-4 w-4 text-white/60" strokeWidth={1.75} />
            <h3 className="font-bold text-white">Score Breakdown</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-sirax-teal mb-2">Factores positivos (Trust)</div>
              {check.breakdown.trust_components?.map((c: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-sm py-1">
                  <span className="text-white/60">{c.label}</span>
                  <span className="text-sirax-teal font-semibold">+{c.points}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-rose-600 mb-2">Factores de riesgo</div>
              {check.breakdown.risk_components?.map((c: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-sm py-1">
                  <span className="text-white/60">{c.label}</span>
                  <span className="text-rose-600 font-semibold">+{c.points}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* AI Report */}
      {check.ai_report && (
        <div className="p-5 rounded-2xl border border-white/8 bg-white/[0.025] sirax-card-glow">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="h-4 w-4 text-sirax-teal" strokeWidth={1.75} />
            <h3 className="font-bold text-white">AI Investigation Report</h3>
            <span className="ml-2 px-2 py-0.5 rounded text-[10px] font-semibold bg-sirax-teal/10 text-sirax-teal uppercase tracking-wider">sirax · AI</span>
          </div>
          <div className="prose prose-sm max-w-none text-white/70">
            {check.ai_report.split('\n').map((line: string, i: number) => {
              if (line.startsWith('## ')) return <h2 key={i} className="text-lg font-bold text-sirax-navy mt-4 mb-2">{line.slice(3)}</h2>
              if (line.startsWith('**') && line.endsWith('**')) return <p key={i} className="font-semibold text-sirax-navy">{line.replace(/\*\*/g, '')}</p>
              if (line.trim() === '') return <br key={i} />
              return <p key={i} className="mb-1">{line}</p>
            })}
          </div>
        </div>
      )}

      {/* Sources */}
      {check.sources_consulted?.length > 0 && (
        <div className="p-4 bg-white/[0.02] rounded-lg border border-white/8">
          <div className="text-xs font-bold uppercase tracking-wider text-white/40 mb-2">Fuentes consultadas</div>
          <div className="flex flex-wrap gap-2">
            {check.sources_consulted.map((s: string, i: number) => (
              <span key={i} className="px-2 py-1 bg-white border border-white/8 rounded text-xs font-mono text-white/60">{s}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ==================== History ====================
function HistoryView() {
  const token = useToken()
  const { navigate } = useRouter()
  const [checks, setChecks] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('')

  useEffect(() => {
    if (token) {
      const params = new URLSearchParams()
      if (search) params.set('q', search)
      if (riskFilter) params.set('risk_level', riskFilter)
      API.get(`/api/checks?${params.toString()}`, token).then(d => { setChecks(Array.isArray(d) ? d : []); setLoading(false) })
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- estado inicial de carga cuando no hay token
      setLoading(false)
    }
  }, [token, search, riskFilter])

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Historial</div>
          <h1 className="text-3xl font-extrabold tracking-tighter text-white">Background Checks</h1>
        </div>
        <button onClick={() => navigate('new-check')}
          className="inline-flex items-center gap-2 bg-sirax-teal text-sirax-navy px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-teal-bright transition-colors">
          <Plus className="h-4 w-4" /> Nuevo Check
        </button>
      </div>

      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            className="w-full pl-10 pr-3 py-2 border border-white/10 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal"
            placeholder="Buscar por nombre..." />
        </div>
        <select value={riskFilter} onChange={e => setRiskFilter(e.target.value)}
          className="px-3 py-2 border border-white/10 rounded-xl text-sm">
          <option value="">Todos los niveles</option>
          <option value="BAJO">Bajo</option>
          <option value="MEDIO">Medio</option>
          <option value="ALTO">Alto</option>
          <option value="CRITICO">Crítico</option>
        </select>
      </div>

      {loading ? <div className="animate-pulse space-y-3">{[1,2,3].map(i => <div key={i} className="h-16 bg-white/8 rounded-lg" />)}</div> : (
        <div className="rounded-2xl border border-white/8 bg-white/[0.025] overflow-hidden">
          <table className="w-full">
            <thead className="bg-white/[0.02]">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Sujeto</th>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Trust</th>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Risk</th>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Nivel</th>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Fecha</th>
                <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40"></th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c: any) => (
                <tr key={c.id} className="border-t border-white/6 hover:bg-white/[0.02] cursor-pointer" onClick={() => navigate('check-results', { checkId: c.id })}>
                  <td className="px-4 py-3 text-sm font-medium text-sirax-navy">{c.subject?.full_name}</td>
                  <td className="px-4 py-3 text-sm font-bold text-sirax-teal">{c.trust_score}</td>
                  <td className="px-4 py-3 text-sm font-bold" style={{ color: RISK_COLORS[c.risk_level] }}>{c.risk_score}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-bold text-white" style={{ backgroundColor: RISK_COLORS[c.risk_level] }}>{c.risk_level}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-white/45 font-mono">{c.created_at?.slice(0, 10)}</td>
                  <td className="px-4 py-3"><ArrowRight className="h-4 w-4 text-white/55" /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {checks.length === 0 && (
            <div className="p-12 text-center text-white/40">
              <FileSearch className="h-8 w-8 mx-auto mb-3" />
              <p>No hay checks. Crea el primero.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ==================== CURP Validator ====================
function CurpValidatorView() {
  const token = useToken()
  const { toast } = useToast()
  const [curp, setCurp] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const validate = async () => {
    setLoading(true)
    const data = await API.post('/api/identity/curp', { curp }, token)
    setResult(data)
    setLoading(false)
    toast({ title: data.is_valid ? 'CURP Válido' : 'CURP Inválido', description: data.message })
  }

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto">
      <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Herramienta</div>
      <h1 className="text-3xl font-extrabold tracking-tighter text-sirax-navy mb-2">Validador de CURP</h1>
      <p className="text-sm text-white/45 mb-6">Validación contra algoritmo oficial mexicano con dígito verificador.</p>

      <div className="bg-white p-6 rounded-lg border border-white/8 space-y-4">
        <div>
          <label className="text-sm font-medium text-white/70 mb-1 block">CURP</label>
          <input value={curp} onChange={e => setCurp(e.target.value.toUpperCase())} maxLength={18}
            className="w-full px-3 py-2 rounded-md text-sm font-mono text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
            placeholder="PEGJ800101HDFRRN09" />
        </div>
        <button onClick={validate} disabled={loading || !curp}
          className="bg-sirax-navy text-white px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft disabled:opacity-50">
          {loading ? 'Validando...' : 'Validar CURP'}
        </button>
      </div>

      {result && (
        <div className={`mt-6 p-6 rounded-lg border ${result.is_valid ? 'border-sirax-teal/40 bg-sirax-teal/5' : 'border-rose-200 bg-rose-50'}`}>
          <div className="flex items-center gap-2 mb-3">
            {result.is_valid ? <CheckCircle2 className="h-5 w-5 text-sirax-teal" /> : <XCircle className="h-5 w-5 text-rose-600" />}
            <span className="font-bold text-lg">{result.is_valid ? 'CURP Válido' : 'CURP Inválido'}</span>
          </div>
          <p className="text-sm">{result.message}</p>
          {result.components && (
            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-white/45">Fecha nacimiento</span><span className="font-medium">{result.components.birth_date}</span></div>
              <div className="flex justify-between"><span className="text-white/45">Sexo</span><span className="font-medium">{result.components.sex}</span></div>
              <div className="flex justify-between"><span className="text-white/45">Estado</span><span className="font-medium">{result.components.state}</span></div>
              <div className="flex justify-between"><span className="text-white/45">Dígito verificador</span><span className="font-medium">{result.check_digit_valid ? '✓ Correcto' : '✗ Incorrecto'}</span></div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ==================== RFC Validator ====================
function RfcValidatorView() {
  const token = useToken()
  const { toast } = useToast()
  const [rfc, setRfc] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const validate = async () => {
    setLoading(true)
    const data = await API.post('/api/identity/rfc', { rfc }, token)
    setResult(data)
    setLoading(false)
    toast({ title: data.is_valid ? 'RFC Válido' : 'RFC Inválido', description: data.message })
  }

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto">
      <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Herramienta</div>
      <h1 className="text-3xl font-extrabold tracking-tighter text-sirax-navy mb-2">Validador de RFC</h1>
      <p className="text-sm text-white/45 mb-6">Validación para persona física (13) y moral (12) con verificación SAT.</p>

      <div className="bg-white p-6 rounded-lg border border-white/8 space-y-4">
        <div>
          <label className="text-sm font-medium text-white/70 mb-1 block">RFC</label>
          <input value={rfc} onChange={e => setRfc(e.target.value.toUpperCase())} maxLength={13}
            className="w-full px-3 py-2 rounded-md text-sm font-mono text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
            placeholder="PEGJ800101AB1" />
        </div>
        <button onClick={validate} disabled={loading || !rfc}
          className="bg-sirax-navy text-white px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft disabled:opacity-50">
          {loading ? 'Validando...' : 'Validar RFC'}
        </button>
      </div>

      {result && (
        <div className={`mt-6 p-6 rounded-lg border ${result.is_valid ? 'border-sirax-teal/40 bg-sirax-teal/5' : 'border-rose-200 bg-rose-50'}`}>
          <div className="flex items-center gap-2 mb-3">
            {result.is_valid ? <CheckCircle2 className="h-5 w-5 text-sirax-teal" /> : <XCircle className="h-5 w-5 text-rose-600" />}
            <span className="font-bold text-lg">{result.is_valid ? 'RFC Válido' : 'RFC Inválido'}</span>
          </div>
          <p className="text-sm">{result.message}</p>
          {result.components && (
            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-white/45">Tipo</span><span className="font-medium">{result.type === 'fisica' ? 'Persona Física' : 'Persona Moral'}</span></div>
              <div className="flex justify-between"><span className="text-white/45">Fecha</span><span className="font-medium">{result.components.date}</span></div>
              <div className="flex justify-between"><span className="text-white/45">SAT Status</span><span className={`font-medium ${result.sat_status === 'ACTIVO' ? 'text-sirax-teal' : 'text-rose-600'}`}>{result.sat_status}</span></div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ==================== Sanctions Screening ====================
function SanctionsView() {
  const token = useToken()
  const { toast } = useToast()
  const [name, setName] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const screen = async () => {
    setLoading(true)
    const data = await API.post('/api/sanctions/screen', { full_name: name }, token)
    setResult(data)
    setLoading(false)
    toast({ title: data.is_sanctioned ? 'ALERTA' : 'Limpio', description: data.is_sanctioned ? 'Match en listas de sanciones' : data.is_pep ? 'PEP detectado' : 'Sin coincidencias' })
  }

  return (
    <div className="p-6 lg:p-8 max-w-3xl mx-auto">
      <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Herramienta</div>
      <h1 className="text-3xl font-extrabold tracking-tighter text-sirax-navy mb-2">Screening de Sanciones</h1>
      <p className="text-sm text-white/45 mb-6">Fuzzy matching contra OFAC, ONU, PEP, SAT 69-B, Interpol y más.</p>

      <div className="bg-white p-6 rounded-lg border border-white/8 space-y-4">
        <div>
          <label className="text-sm font-medium text-white/70 mb-1 block">Nombre completo</label>
          <input value={name} onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-md text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-sirax-teal focus:border-sirax-teal border border-white/10 bg-white/5"
            placeholder="Juan Pérez García" />
        </div>
        <button onClick={screen} disabled={loading || !name}
          className="bg-sirax-navy text-white px-5 py-2.5 rounded-md font-semibold text-sm hover:bg-sirax-navy-soft disabled:opacity-50">
          {loading ? 'Screening...' : 'Ejecutar Screening'}
        </button>
      </div>

      {result && (
        <div className={`mt-6 p-6 rounded-lg border ${result.is_sanctioned ? 'border-rose-200 bg-rose-50' : result.is_pep ? 'border-amber-200 bg-amber-50' : 'border-sirax-teal/40 bg-sirax-teal/5'}`}>
          <div className="flex items-center gap-2 mb-3">
            {result.is_sanctioned ? <XCircle className="h-5 w-5 text-rose-600" /> : result.is_pep ? <AlertTriangle className="h-5 w-5 text-amber-600" /> : <CheckCircle2 className="h-5 w-5 text-sirax-teal" />}
            <span className="font-bold text-lg">
              {result.is_sanctioned ? 'Match en Listas de Sanciones' : result.is_pep ? 'Persona Expuesta Políticamente' : 'Sin Coincidencias'}
            </span>
          </div>

          {result.matches?.length > 0 && (
            <div className="mt-4 space-y-3">
              <h4 className="text-sm font-bold text-sirax-navy">Coincidencias:</h4>
              {result.matches.map((m: any, i: number) => (
                <div key={i} className="p-3 bg-white rounded border border-white/8">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sirax-navy">{m.matched_name}</span>
                    <span className="px-2 py-0.5 rounded text-xs font-bold bg-white/5">{m.score}%</span>
                  </div>
                  <div className="text-xs text-white/45 mt-1">{m.list_name} · {m.type} · {m.country} · {m.program}</div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-4 text-xs text-white/40">
            {result.lists_checked?.length} listas consultadas · {result.total_records_screened} registros · Threshold: {result.threshold_used}%
          </div>
        </div>
      )}
    </div>
  )
}

// ==================== API Docs ====================
function ApiDocsView() {
  const endpoints = [
    { method: 'POST', path: '/api/auth/register', desc: 'Crear cuenta', body: '{ email, password, fullName }' },
    { method: 'POST', path: '/api/auth/login', desc: 'Iniciar sesión', body: '{ email, password }' },
    { method: 'POST', path: '/api/identity/curp', desc: 'Validar CURP', body: '{ curp, full_name? }' },
    { method: 'POST', path: '/api/identity/rfc', desc: 'Validar RFC', body: '{ rfc }' },
    { method: 'POST', path: '/api/government/renapo', desc: 'Consulta RENAPO', body: '{ curp }' },
    { method: 'POST', path: '/api/government/sat', desc: 'Consulta SAT', body: '{ rfc }' },
    { method: 'POST', path: '/api/sanctions/screen', desc: 'Screening sanciones', body: '{ full_name, threshold? }' },
    { method: 'POST', path: '/api/digital/email', desc: 'Inteligencia de email', body: '{ email }' },
    { method: 'POST', path: '/api/digital/phone', desc: 'Inteligencia de teléfono', body: '{ phone }' },
    { method: 'POST', path: '/api/digital/username', desc: 'Descubrimiento de username', body: '{ username }' },
    { method: 'POST', path: '/api/checks', desc: 'Background check completo', body: '{ full_name, curp?, rfc?, email?, phone?, username?, include_*? }' },
    { method: 'GET', path: '/api/checks', desc: 'Listar checks', body: '?q=&risk_level=' },
    { method: 'GET', path: '/api/checks/:id', desc: 'Detalle de check', body: '' },
    { method: 'GET', path: '/api/analytics/dashboard', desc: 'Dashboard analytics', body: '' },
  ]

  return (
    <div className="p-6 lg:p-8 max-w-4xl mx-auto">
      <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-sirax-teal mb-1.5">Documentación</div>
      <h1 className="text-3xl font-extrabold tracking-tighter text-sirax-navy mb-2">API Reference</h1>
      <p className="text-sm text-white/45 mb-6">REST API para integraciones con CRMs, ERPs, fintechs y bancos.</p>

      <div className="rounded-2xl border border-white/8 bg-white/[0.025] overflow-hidden">
        <table className="w-full">
          <thead className="bg-white/[0.02]">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Method</th>
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Endpoint</th>
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Descripción</th>
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-white/40">Body / Params</th>
            </tr>
          </thead>
          <tbody>
            {endpoints.map((ep, i) => (
              <tr key={i} className="border-t border-white/6">
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${ep.method === 'POST' ? 'bg-sirax-teal/15 text-sirax-teal' : 'bg-sky-100 text-sky-700'}`}>{ep.method}</span>
                </td>
                <td className="px-4 py-3 text-xs font-mono text-sirax-navy">{ep.path}</td>
                <td className="px-4 py-3 text-sm text-white/60">{ep.desc}</td>
                <td className="px-4 py-3 text-xs font-mono text-white/40">{ep.body}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 p-6 bg-sirax-navy rounded-lg text-white">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-bold uppercase tracking-wider text-white/40">Ejemplo: Background Check completo</div>
          <span className="text-[10px] font-mono text-sirax-teal">sirax API · v1</span>
        </div>
        <pre className="text-xs font-mono text-white/55 leading-relaxed overflow-x-auto">{`curl -X POST /api/checks \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "full_name": "Juan Pérez García",
    "curp": "PEGJ800101HDFRRN09",
    "rfc": "PEGJ800101AB1",
    "email": "juan@empresa.mx",
    "include_ai_report": true
  }'

# Response:
# trust_score: 92 | risk_level: BAJO | recommendation: APPROVE`}</pre>
      </div>
    </div>
  )
}

// ==================== Main App ====================
export default function Home() {
  const [view, setView] = useState<View>('landing')
  const [viewData, setViewData] = useState<any>(null)
  const [mounted, setMounted] = useState(false)
  const { user, login: authLogin, logout: authLogout } = useAuth()

  // After mount, read localStorage and set correct view
  useEffect(() => {
    const savedView = (localStorage.getItem('sirax_view') || localStorage.getItem('synkdata_view')) as View | null
    const token = localStorage.getItem('sirax_token') || localStorage.getItem('synkdata_token')
    if (token && user) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hidratación única de la vista al montar
      setView(savedView && savedView !== 'landing' && savedView !== 'login' && savedView !== 'register' ? savedView : 'dashboard')
    } else if (token && !user) {
      // Token exists but user not loaded yet - will be handled by auth provider
      setView('dashboard')
    } else {
      setView('landing')
    }
    setMounted(true)
  }, [])

  // Also redirect when user changes after mount
  useEffect(() => {
    if (!mounted) return
    if (user && (view === 'landing' || view === 'login' || view === 'register')) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- redirección controlada tras cambio de sesión
      setView('dashboard')
      localStorage.setItem('sirax_view', 'dashboard')
    }
  }, [user, mounted, view])

  const navigate = useCallback((v: View, data?: any) => {
    setView(v)
    setViewData(data || null)
    if (typeof window !== 'undefined') {
      localStorage.setItem('sirax_view', v)
    }
  }, [])

  const renderView = () => {
    // If not mounted yet (SSR/hydration), show nothing
    if (!mounted) return <div className="min-h-screen bg-white" />

    switch (view) {
      case 'landing': return <LandingView />
      case 'login': return user ? <DashboardLayout><DashboardView /></DashboardLayout> : <LoginView />
      case 'register': return user ? <DashboardLayout><DashboardView /></DashboardLayout> : <RegisterView />
      case 'dashboard': return <DashboardLayout><DashboardView /></DashboardLayout>
      case 'new-check': return <DashboardLayout><NewCheckView /></DashboardLayout>
      case 'check-results': return <DashboardLayout><CheckResultsView /></DashboardLayout>
      case 'history': return <DashboardLayout><HistoryView /></DashboardLayout>
      case 'curp': return <DashboardLayout><CurpValidatorView /></DashboardLayout>
      case 'rfc': return <DashboardLayout><RfcValidatorView /></DashboardLayout>
      case 'sanctions': return <DashboardLayout><SanctionsView /></DashboardLayout>
      case 'api-docs': return <DashboardLayout><ApiDocsView /></DashboardLayout>
      default: return <LandingView />
    }
  }

  return (
    <AuthProvider>
      <RouterContext.Provider value={{ view, navigate, viewData }}>
        {renderView()}
      </RouterContext.Provider>
    </AuthProvider>
  )
}
