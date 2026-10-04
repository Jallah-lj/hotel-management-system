import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, Archive, ArrowDownRight, ArrowUpRight, Ban, BedDouble, Bell, CalendarDays, Check, ChevronRight, CircleDollarSign, ClipboardCheck, Coffee, Copy, Eye, EyeOff, FileText, Globe, Hotel, House, LayoutDashboard, LogIn, LogOut, Mail, Menu, Moon, MoreHorizontal, PanelLeftClose, Pencil, Phone, Play, Plus, Receipt, RefreshCw, Search, Settings, ShieldCheck, Sparkles, UserRound, Users, Wrench, X } from 'lucide-react'
import { ApiRequestError, api, clearSession, Dashboard, Guest, isPreviewHost, Page, Payment, rememberUser, rememberedUser, Reservation, Room, Service, Task, Ticket, User } from './lib/api'

const money = (value: string | number | undefined) => `${Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const pretty = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())

// -- Lightweight feedback toasts -------------------------------------------
type ToastItem = { id: number; text: string; tone: 'ok' | 'err' }
let pushToast: ((t: ToastItem) => void) | null = null
function toast(text: string, tone: 'ok' | 'err' = 'ok') { pushToast?.({ id: Date.now() + Math.random(), text, tone }) }
function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([])
  useEffect(() => {
    pushToast = (t) => { setItems((current) => [...current, t]); setTimeout(() => setItems((current) => current.filter((x) => x.id !== t.id)), 4200) }
    return () => { pushToast = null }
  }, [])
  return <div className="toast-host">{items.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}</div>
}

// -- Row "three dots" menu ---------------------------------------------------
type MenuAction = { label: string; icon?: React.ElementType; danger?: boolean; disabled?: boolean; onClick: () => void }
function RowMenu({ actions, size = 17, align = 'right' }: { actions: MenuAction[]; size?: number; align?: 'right' | 'left' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onPointer); document.removeEventListener('keydown', onKey) }
  }, [open])
  return <div className="row-menu-wrap" ref={ref}>
    <button type="button" className={`icon-button ${open ? 'menu-open' : ''}`} aria-haspopup="menu" aria-expanded={open} onClick={(event) => { event.stopPropagation(); setOpen((value) => !value) }}><MoreHorizontal size={size} /></button>
    {open && <div className={`row-menu ${align}`} role="menu">{actions.map((a) => <button type="button" key={a.label} role="menuitem" disabled={a.disabled} className={a.danger ? 'danger' : ''} onClick={(event) => { event.stopPropagation(); setOpen(false); a.onClick() }}>{a.icon && <a.icon size={14} />}{a.label}</button>)}</div>}
  </div>
}

// -- Confirmation dialog (optionally requiring a reason) --------------------
function ConfirmModal({ title, subtitle, confirmLabel = 'Confirm', requireReason = false, onConfirm, onClose }: { title: string; subtitle: string; confirmLabel?: string; requireReason?: boolean; onConfirm: (reason: string) => Promise<void>; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function run(event: React.FormEvent) {
    event.preventDefault()
    if (requireReason && reason.trim().length < 2) { setError('Please give a short reason.') ; return }
    setBusy(true)
    try { await onConfirm(reason.trim()); onClose() } catch (err) { setError(err instanceof Error ? err.message : 'The action failed. Please try again.') } finally { setBusy(false) }
  }
  return <Modal title={title} subtitle={subtitle} onClose={onClose}><form className="modal-form" onSubmit={run}>{requireReason && <label>Reason<textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="Recorded in the audit log" /></label>}{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label={confirmLabel} /></form></Modal>
}

// -- Run a row action with toast feedback ------------------------------------
function useRowActions(reload: () => Promise<void> | void) {
  const [busyId, setBusyId] = useState('')
  async function act(id: string, fn: () => Promise<unknown>, message: string) {
    setBusyId(id)
    try { await fn(); toast(message); await reload() } catch (e) { toast(e instanceof Error ? e.message : 'The action failed.', 'err') } finally { setBusyId('') }
  }
  return { busyId, act }
}
const loginErrorMessage = (error: unknown) => error instanceof ApiRequestError && error.status === 401 ? 'We could not complete the sign-in session. Please try again.' : error instanceof Error ? error.message : 'Unable to sign in.'

function Login({ onLogin, notice }: { onLogin: (user: User) => void; notice?: string }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [sandboxBusy, setSandboxBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  async function useDevelopmentAccount() {
    setSandboxBusy(true); setError('')
    try {
      const response = await api<{ user: User }>('/auth/demo-login', { method: 'POST' })
      onLogin(response.user)
    } catch (e) {
      setError(loginErrorMessage(e))
    } finally { setSandboxBusy(false) }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError('')
    if (isPreviewHost()) console.info('[AUTH] login form submitted')
    if (!email.trim() || !password) {
      setError('Enter your work email and password to continue.')
      return
    }
    setBusy(true)
    try {
      const response = await api<{ user: User; access_token?: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      if (isPreviewHost()) console.info('[AUTH] login accepted', { email: response.user.email, hasAccessToken: Boolean(response.access_token) })
      // The backend has already authenticated this credential. The dashboard
      // API performs the next authenticated request; do not introduce a
      // second login-time request that can race cookie/session restoration.
      onLogin(response.user)
    } catch (e) { if (isPreviewHost()) console.info('[AUTH] login failed', { message: e instanceof Error ? e.message : 'unknown error' }); setError(loginErrorMessage(e)) }
    finally { setBusy(false) }
  }
  return <main className="login-page">
    <section className="login-visual"><div className="login-mark"><Hotel size={22} strokeWidth={1.8} /><span>AURORA GRAND</span></div><div className="visual-copy"><span className="eyebrow light">OPERATIONS WORKSPACE</span><h1>Every stay,<br /><em>beautifully</em> handled.</h1><p>A single, calm command center for the people who make every arrival feel effortless.</p></div><div className="visual-foot"><span>EST. 1998</span><span>HARBOR DISTRICT · NEW YORK</span></div></section>
    <section className="login-form-wrap"><div className="login-form"><div className="mobile-mark"><Hotel size={19} /><span>AURORA GRAND</span></div><span className="eyebrow">STAFF PORTAL</span><h2>Welcome back</h2><p className="muted">Sign in to continue to your hotel workspace.</p>{notice && <div className="form-error"><AlertTriangle size={16} />{notice}</div>}<form onSubmit={submit}><label>Work email or username<input autoFocus type="text" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@auroragrand.example" autoComplete="username" /></label><label>Password<div className="password-field"><input type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" autoComplete="current-password" /><button type="button" className="reveal" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<button className="primary-button wide" disabled={busy}>{busy ? <span className="spinner" /> : <><span>Sign in securely</span><ChevronRight size={17} /></>}</button>{isPreviewHost() && <button type="button" className="secondary-button wide sandbox-button" onClick={useDevelopmentAccount} disabled={busy || sandboxBusy}>{sandboxBusy ? <span className="spinner dark" /> : <><span>Use development account</span><ChevronRight size={17} /></>}</button>}</form><div className="login-help"><ShieldCheck size={15} /><span>Protected with encrypted sessions and role-based access.</span></div></div></section>
  </main>
}

type NavItem = { label: string; icon: React.ElementType; to: string; permission?: string }
const primaryNav: NavItem[] = [{ label: 'Overview', icon: LayoutDashboard, to: '/dashboard' }, { label: 'Reservations', icon: CalendarDays, to: '/reservations' }, { label: 'Guests', icon: Users, to: '/guests' }, { label: 'Rooms & rates', icon: BedDouble, to: '/rooms' }]
const operationsNav: NavItem[] = [{ label: 'Housekeeping', icon: Sparkles, to: '/housekeeping' }, { label: 'Maintenance', icon: Wrench, to: '/maintenance' }, { label: 'Services & dining', icon: Coffee, to: '/services' }]
const financeNav: NavItem[] = [{ label: 'Payments', icon: CircleDollarSign, to: '/finance' }, { label: 'Reports', icon: FileText, to: '/reports' }]

type PublicHotel = { hotel: { name: string; tagline: string; phone: string; email: string; address: string; check_in_time: string; check_out_time: string; currency: string }; room_types: { id: string; code: string; name: string; description: string; base_price: number; weekend_price: number | null; size_sqm: number | null; max_occupancy: number; bed_type: string; amenities: string[] }[]; services: { code: string; name: string; description: string; category: string; price: number; unit: string; requires_scheduling: boolean }[] }
const SERVICE_ICONS: Record<string, React.ElementType> = { dining: Coffee, wellness: Sparkles, transport: Hotel, general: Sparkles }
function VisitorHome({ onStaffLogin, inWorkspace = false }: { onStaffLogin: () => void; inWorkspace?: boolean }) {
  const [data, setData] = useState<PublicHotel | null>(null)
  useEffect(() => { api<PublicHotel>('/public/hotel').then(setData).catch(() => undefined) }, [])
  const h = data?.hotel
  const servicesByCategory = useMemo(() => { const grouped: Record<string, NonNullable<PublicHotel>['services']> = {}; for (const s of data?.services ?? []) (grouped[s.category] ??= []).push(s); return grouped }, [data])
  return <main className="visitor-home">
    <header className="visitor-nav"><div className="visitor-brand"><span className="brand-icon"><Hotel size={18} /></span><span>AURORA <b>GRAND</b></span></div><button className="secondary-button visitor-login" onClick={onStaffLogin}>{inWorkspace ? 'Open workspace' : 'Staff sign in'} <ChevronRight size={15} /></button></header>
    <section className="visitor-hero"><div className="visitor-hero-copy"><span className="eyebrow">{(h?.name ?? 'Aurora Grand Hotel').toUpperCase()} · HARBOR DISTRICT</span><h1>A quieter kind<br />of <em>luxury.</em></h1><p>{h?.tagline || 'Thoughtful rooms, warm service, and a stay shaped around the way you want to feel when you arrive.'}</p><div className="visitor-actions"><button className="primary-button" onClick={() => document.getElementById('visitor-features')?.scrollIntoView({ behavior: 'smooth' })}>Explore the hotel <ChevronRight size={16} /></button><button className="text-button" onClick={onStaffLogin}>{inWorkspace ? 'Back to the workspace' : 'Hotel staff sign in'} <ChevronRight size={15} /></button></div></div><div className="visitor-hero-card"><span className="visitor-card-kicker">THE AURORA EXPERIENCE</span><strong>Stay a little<br /><em>longer.</em></strong><span className="visitor-card-meta">{data ? `${data.room_types.length} room types · ${data.services.length} services` : 'Rooms · Dining · Wellness'}</span></div></section>
    <section className="visitor-intro"><div><span className="eyebrow">A PLACE TO ARRIVE</span><h2>Made for unhurried mornings and memorable evenings.</h2></div><p>From the first welcome to the final coffee, every detail at Aurora Grand is considered with care. Discover a modern landmark with the soul of a private residence.</p></section>
    <section id="visitor-features" className="visitor-features"><article><BedDouble size={20} /><span className="eyebrow">ROOMS & SUITES</span><h3>Rest beautifully</h3><p>Calm interiors, considered comforts, and views that make the city feel far away.</p></article><article><Coffee size={20} /><span className="eyebrow">DINING</span><h3>Gather well</h3><p>Seasonal plates and effortless service from breakfast through late evening.</p></article><article><Sparkles size={20} /><span className="eyebrow">WELLNESS</span><h3>Find your pace</h3><p>A quiet retreat for restorative treatments, movement, and time to yourself.</p></article></section>
    {data && data.room_types.length > 0 && <section className="visitor-rooms"><div className="visitor-section-head"><span className="eyebrow">ROOMS & SUITES</span><h2>Choose your stay</h2><p>Live from our reservations catalogue — rates per night.</p></div><div className="visitor-room-grid">{data.room_types.map((rt) => <article className="visitor-room-card" key={rt.id}><div className="visitor-room-top"><strong>{rt.name}</strong><span>{rt.code}</span></div><p>{rt.description}</p><div className="visitor-room-meta"><span><BedDouble size={13} />{pretty(rt.bed_type)} · sleeps {rt.max_occupancy}</span>{rt.size_sqm ? <span><House size={13} />{rt.size_sqm} m²</span> : null}</div>{rt.amenities.length > 0 && <div className="visitor-amenities">{rt.amenities.slice(0, 4).map((a) => <em key={a}>{a}</em>)}{rt.amenities.length > 4 ? <em>+{rt.amenities.length - 4} more</em> : null}</div>}<div className="visitor-room-price"><strong>${money(String(rt.base_price))}</strong><span>per night</span></div></article>)}</div></section>}
    {data && data.services.length > 0 && <section className="visitor-services"><div className="visitor-section-head"><span className="eyebrow">FEATURES & SERVICES</span><h2>Everything a stay can ask for</h2><p>Available to every guest — prices include our standard service.</p></div><div className="visitor-service-grid">{Object.entries(servicesByCategory).map(([category, items]) => { const Icon = SERVICE_ICONS[category] ?? Sparkles; return <article className="visitor-service-card" key={category}><header><Icon size={17} /><h3>{pretty(category)}</h3></header>{items.map((s) => <div className="visitor-service-row" key={s.code}><div><strong>{s.name}</strong>{s.description ? <small>{s.description}</small> : null}</div><span>${money(String(s.price))} <i>{s.unit}</i></span></div>)}</article> })}</div></section>}
    {h && <section className="visitor-info"><div><span className="eyebrow">VISIT US</span><h2>{h.name}</h2></div><div className="visitor-info-grid"><div><Phone size={16} /><strong>Call the front desk</strong><span>{h.phone || '—'}</span></div><div><Mail size={16} /><strong>Reservations</strong><span>{h.email || '—'}</span></div><div><Hotel size={16} /><strong>Find us</strong><span>{h.address || '—'}</span></div><div><CalendarDays size={16} /><strong>Arrivals & departures</strong><span>Check-in {h.check_in_time} · check-out {h.check_out_time}</span></div></div></section>}
    <footer className="visitor-footer"><span>© 2026 {h?.name ?? 'Aurora Grand Hotel'}</span><button className="text-button" onClick={() => window.location.assign('/policy')}>Privacy &amp; Policy</button><span>{h?.address || 'Harbor District'}</span></footer>
  </main>
}

function PolicyPage({ onBack }: { onBack: () => void }) {
  const sections: { id: string; title: string; body: string[] }[] = [
    { id: 'overview', title: '1. Overview', body: [
      'This Privacy & Policy notice explains what information Aurora Grand Hotel ("we", "us") collects when you use our website, booking services and on-property systems, why we collect it, and the choices you have.',
      'By making a reservation, checking in, or using the guest services at Aurora Grand Hotel, you agree to the practices described on this page. The policy applies to guests, visitors to this website, and anyone who contacts our reservations team.'] },
    { id: 'collect', title: '2. Information we collect', body: [
      'Identity & contact details — full name, email address, phone number and nationality, provided when a booking is created or a guest profile is opened.',
      'Stay details — arrival and departure dates, room type, number of guests, special requests and service orders (dining, spa, transfers).',
      'Payment information — amounts, method and a non-sensitive external reference (authorisation code or transfer ID). We never store card numbers, CVV codes or bank credentials; payment instruments are handled by your bank or payment provider.',
      'Identity verification — where local law requires, a government ID may be inspected at check-in. Only the minimum fields required by law are recorded.',
      'Technical data — anonymous request identifiers and error references used to keep our systems healthy and secure.'] },
    { id: 'use', title: '3. How we use your information', body: [
      'To fulfil your reservation: assign rooms, prepare arrivals, issue invoices and settle folios.',
      'To operate hotel services: housekeeping scheduling, maintenance responses, and dining or wellness orders attached to your stay.',
      'To communicate with you about your stay — arrival instructions, schedule changes, or responses to requests you make.',
      'For legitimate business operations: aggregated occupancy and revenue reporting. These reports use totals and trends only, never your name.',
      'To meet legal obligations: tax records, lodging registers and audit trails required of licensed hotels.'] },
    { id: 'sharing', title: '4. What we never do', body: [
      'We do not sell guest data, and we do not share personal information with third parties for marketing.',
      'We disclose information only where required by law (for example a valid court order), or to the limited processors that help us run the hotel — each bound by confidentiality.'] },
    { id: 'retention', title: '5. Retention', body: [
      'Guest and reservation records are kept for the period required by hospitality and tax regulation, after which they are archived or securely deleted.',
      'Payment entries are retained as financial records; card details are never retained because they are never stored.',
      'You may ask us to correct your details or close your guest profile at any time, subject to legal retention duties.'] },
    { id: 'security', title: '6. Security', body: [
      'Access to guest data inside our operations workspace is role-based: staff see only what their role requires, and every sensitive action is written to an audit trail.',
      'Connections are encrypted in transit, passwords are stored only as salted hashes, and sessions expire automatically.',
      'If you believe you have found a security issue, contact us immediately — we treat every report as urgent.'] },
    { id: 'cookies', title: '7. Cookies & sessions', body: [
      'This site uses a first-party session cookie strictly to keep staff signed in to the operations workspace. Guest-facing pages set no tracking cookies and run no advertising or analytics trackers.'] },
    { id: 'rights', title: '8. Your rights & contact', body: [
      'You may request a copy of the personal information we hold about you, ask for corrections, or raise a concern at any time.',
      'Contact the Front Desk: stay@auroragrand.example · +1 555 014 2040, or write to Aurora Grand Hotel, 18 Meridian Avenue, Harbor District.',
      'This policy was last updated on October 4, 2026.'] },
  ]
  return <main className="visitor-home policy-page">
    <header className="visitor-nav"><button className="text-button" onClick={onBack}><ChevronRight size={15} style={{ transform: 'rotate(180deg)' }} /> Back to the hotel site</button><div className="visitor-brand"><span className="brand-icon"><Hotel size={18} /></span><span>AURORA <b>GRAND</b></span></div></header>
    <section className="policy-hero"><span className="eyebrow">AURORA GRAND HOTEL</span><h1>Privacy &amp; Policy</h1><p>Plain language about the information we keep, why we keep it, and how it stays protected. Last updated October 4, 2026.</p></section>
    <div className="policy-layout">
      <nav className="policy-toc">{sections.map((s) => <a key={s.id} href={`#${s.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth' }) }}>{s.title}</a>)}</nav>
      <div className="policy-body">{sections.map((s) => <section key={s.id} id={s.id}><h2>{s.title}</h2>{s.body.map((p, i) => <p key={i}>{p}</p>)}</section>)}</div>
    </div>
    <footer className="visitor-footer"><span>© 2026 Aurora Grand Hotel</span><span>18 Meridian Avenue, Harbor District</span></footer>
  </main>
}

function App() {
  const cachedUser = rememberedUser()
  const location = useLocation()
  const navigate = useNavigate()
  // Set once the backend confirms whether sign-in is disabled for testing.
  // `null` means the configuration probe has not answered yet.
  const [authConfig, setAuthConfig] = useState<{ login_disabled: boolean } | null>(null)
  const loginDisabled = authConfig?.login_disabled ?? false
  const shouldRestoreSession = location.pathname !== '/' || Boolean(cachedUser) || loginDisabled
  const [user, setUser] = useState<User | null>(cachedUser)
  const [checking, setChecking] = useState(shouldRestoreSession)
  const [authError, setAuthError] = useState('')
  // Set when the automatic test sign-in fails: the tester is dropped back to
  // the manual login form so the workspace is never unreachable.
  const [autoSignInFailed, setAutoSignInFailed] = useState(false)
  const bootstrapController = useRef<AbortController | null>(null)
  useEffect(() => {
    let active = true
    // Never strand the UI on a spinner if the configuration probe cannot
    // complete (slow or restrictive preview proxies): fall back to the normal
    // login page. The first resolution wins so a late response cannot flip
    // the mode after the user has already acted.
    const fallback = setTimeout(() => { if (active) setAuthConfig((prev) => prev ?? { login_disabled: false }) }, 6000)
    api<{ login_disabled: boolean }>('/auth/config')
      .then((config) => { if (active) setAuthConfig((prev) => prev ?? config) })
      .catch(() => { if (active) setAuthConfig((prev) => prev ?? { login_disabled: false }) })
      .finally(() => clearTimeout(fallback))
    return () => { active = false; clearTimeout(fallback) }
  }, [])
  useEffect(() => {
    if (!shouldRestoreSession) return
    const controller = new AbortController()
    let cancelled = false
    bootstrapController.current = controller
    // Never spin forever if the workspace cannot be opened: surface a retry
    // error instead of an endless loading screen.
    const watchdog = setTimeout(() => controller.abort(), 20000)
    const bootstrap = async () => {
      setChecking(true)
      if (isPreviewHost()) console.info('[AUTH] restoring session', { loginDisabled })
      try {
        let sessionUser: User
        if (loginDisabled) {
          // Login is disabled while the platform is being tested: the backend
          // resolves /auth/me to the seeded development account, so one GET
          // opens the workspace with no cookies and no sign-in request. If
          // that still fails, fall back to the explicit demo sign-in.
          try {
            sessionUser = await api<User>('/auth/me', { signal: controller.signal })
          } catch (meError) {
            if (controller.signal.aborted) throw meError
            const session = await api<{ user: User }>('/auth/demo-login', { method: 'POST', signal: controller.signal })
            sessionUser = session.user
          }
        } else {
          sessionUser = await api<User>('/auth/me', { signal: controller.signal })
        }
        if (cancelled) return
        if (isPreviewHost()) console.info('[AUTH] session ready', { email: sessionUser.email })
        rememberUser(sessionUser)
        setUser(sessionUser)
        setAuthError('')
        if (location.pathname === '/' || location.pathname === '/login') navigate('/dashboard', { replace: true })
      } catch (error) {
        if (cancelled) return
        if (controller.signal.aborted) {
          setAuthError('The workspace took too long to respond. Please try again.')
          return
        }
        if (isPreviewHost()) console.info('[AUTH] session restore failed', { status: error instanceof ApiRequestError ? error.status : 0, message: error instanceof Error ? error.message : 'unknown error', loginDisabled })
        if (error instanceof ApiRequestError && error.status === 401) {
          clearSession()
          setUser(null)
          // The automatic test account could not be opened: fall back to the
          // manual login form instead of leaving the tester on a spinner.
          if (loginDisabled) setAutoSignInFailed(true)
        } else if (loginDisabled) {
          // Any other automatic sign-in failure also falls back to the manual
          // form so the workspace remains reachable while testing.
          setAutoSignInFailed(true)
        } else {
          setAuthError(error instanceof Error ? error.message : 'Unable to verify your hotel session.')
        }
      } finally {
        clearTimeout(watchdog)
        if (!cancelled) setChecking(false)
      }
    }
    const logout = () => { clearSession(); setUser(null); setAuthError('') }
    window.addEventListener('hms:unauthorized', logout)
    void bootstrap()
    return () => {
      cancelled = true
      controller.abort()
      if (bootstrapController.current === controller) bootstrapController.current = null
      window.removeEventListener('hms:unauthorized', logout)
    }
    // location/navigate are intentionally not dependencies: the bootstrap must
    // only re-run when the session strategy changes, not on every navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldRestoreSession, loginDisabled])
  const handleLogin = (loggedInUser: User) => {
    // A late unauthenticated bootstrap response must never clear this newly
    // authenticated session.
    bootstrapController.current?.abort()
    rememberUser(loggedInUser)
    setAuthError('')
    setUser(loggedInUser)
    if (isPreviewHost()) console.info('[AUTH] navigating to /dashboard')
    navigate('/dashboard', { replace: true })
  }
  const handleLogout = () => {
    api('/auth/logout', { method: 'POST' }).finally(() => {
      clearSession()
      setUser(null)
      navigate('/login', { replace: true })
    })
  }
  // The guest-facing homepage is public and must render even while the
  // workspace session is still bootstrapping (or while login is disabled).
  if (location.pathname === '/home') return <VisitorHome inWorkspace={Boolean(user)} onStaffLogin={() => navigate(user ? '/' : '/login')} />
  if (location.pathname === '/policy' || location.pathname === '/privacy') return <PolicyPage onBack={() => navigate('/home')} />
  if (checking) return <div className="app-loading"><div className="brand-loader"><Hotel size={22} /><span>AURORA GRAND</span></div><span className="spinner dark" /></div>
  if (authError) return <ErrorState message={authError} />
  if (!user) {
    if (!autoSignInFailed && (authConfig === null || loginDisabled)) return <div className="app-loading"><div className="brand-loader"><Hotel size={22} /><span>AURORA GRAND</span></div><span className="muted">Sign-in is disabled — opening the test workspace…</span><span className="spinner dark" /></div>
    if (autoSignInFailed) return <Login onLogin={handleLogin} notice="The automatic test sign-in could not be completed. Use the development account button, or the seeded credentials from the README." />
    return location.pathname === '/' ? <VisitorHome onStaffLogin={() => navigate('/login')} /> : <Login onLogin={handleLogin} />
  }
  return <AppShell user={user} onLogout={handleLogout} testMode={loginDisabled} />
}

function timeAgo(iso: string) { const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000); if (seconds < 60) return 'just now'; const minutes = seconds / 60; if (minutes < 60) return `${Math.floor(minutes)}m ago`; const hours = minutes / 60; if (hours < 24) return `${Math.floor(hours)}h ago`; return `${Math.floor(hours / 24)}d ago` }

type NotifItem = { id: string; title: string; message: string; category: string; severity: string; is_read: boolean; link: string | null; created_at: string }
function NotificationBell() {
  const [open, setOpen] = useState(false); const [items, setItems] = useState<NotifItem[]>([]); const [unread, setUnread] = useState(0)
  const ref = useRef<HTMLDivElement>(null); const navigate = useNavigate()
  const refreshUnread = useCallback(() => { api<Page<NotifItem>>('/notifications?unread_only=true&page_size=1').then((p) => setUnread(p.total)).catch(() => undefined) }, [])
  useEffect(() => { refreshUnread(); const timer = setInterval(refreshUnread, 45000); return () => clearInterval(timer) }, [refreshUnread])
  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onPointer); document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onPointer); document.removeEventListener('keydown', onKey) }
  }, [open])
  function toggle() { const next = !open; setOpen(next); if (next) api<Page<NotifItem>>('/notifications?page_size=8').then((p) => setItems(p.items)).catch(() => undefined) }
  const markRead = (n: NotifItem) => api(`/notifications/${n.id}/read`, { method: 'POST' }).then(() => { setItems((current) => current.map((x) => (x.id === n.id ? { ...x, is_read: true } : x))); refreshUnread() }).catch(() => undefined)
  const markAll = () => api('/notifications/read-all', { method: 'POST' }).then(() => { setItems((current) => current.map((x) => ({ ...x, is_read: true }))); setUnread(0) }).catch(() => undefined)
  return <div className="notif-wrap" ref={ref}>
    <button type="button" className="icon-button notification-button" aria-label="Notifications" onClick={toggle}><Bell size={18} />{unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}</button>
    {open && <div className="notif-pop">
      <div className="notif-head"><strong>Notifications</strong>{unread > 0 && <button type="button" className="text-button" onClick={markAll}>Mark all read</button>}</div>
      {items.length === 0 ? <div className="notif-empty"><Bell size={18} /><span>You're all caught up.</span></div> : items.map((n) => <button type="button" key={n.id} className={`notif-item ${n.is_read ? 'read' : ''}`} onClick={() => { markRead(n); if (n.link) { setOpen(false); navigate(n.link) } }}>
        <span className={`notif-dot ${n.severity}`} />
        <span className="notif-copy"><strong>{n.title}</strong><small>{n.message}</small><em>{timeAgo(n.created_at)} · {pretty(n.category)}</em></span>
        {!n.is_read && <i className="notif-unread" />}
      </button>)}
    </div>}
  </div>
}

function AppShell({ user, onLogout, testMode = false }: { user: User; onLogout: () => void; testMode?: boolean }) {
  const [sidebar, setSidebar] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const title = location.pathname === '/' || location.pathname === '/dashboard' ? 'Good morning, Avery' : pretty(location.pathname.slice(1).split('/')[0])
  return <div className={`app-shell ${sidebar ? '' : 'sidebar-collapsed'}`}><aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}><div className="sidebar-top"><div className="brand"><span className="brand-icon"><Hotel size={18} /></span><span className="brand-text">AURORA <b>GRAND</b></span></div><button className="icon-button sidebar-close" onClick={() => setMobileOpen(false)}><X size={18} /></button></div><nav><NavSection label="WORKSPACE" items={primaryNav} onNavigate={() => setMobileOpen(false)} /><NavSection label="OPERATIONS" items={operationsNav} onNavigate={() => setMobileOpen(false)} /><NavSection label="FINANCE" items={financeNav} onNavigate={() => setMobileOpen(false)} /></nav><div className="sidebar-bottom"><NavLink to="/settings" className="nav-item" onClick={() => setMobileOpen(false)}><Settings size={17} /><span>Settings</span></NavLink><div className="user-mini"><div className="avatar">{user.first_name[0]}{user.last_name[0]}</div><div className="user-mini-copy"><strong>{user.full_name}</strong><small>{user.roles[0]?.name ?? 'Staff'}</small></div>{testMode ? <span className="test-mode-chip" title="Login is disabled while the platform is being tested">TEST MODE</span> : <button className="icon-button" onClick={onLogout} title="Sign out"><LogOut size={16} /></button>}</div></div></aside><div className="main-area"><header className="topbar"><div className="topbar-left"><button className="icon-button menu-toggle" onClick={() => setMobileOpen(true)}><Menu size={20} /></button><button className="icon-button collapse-toggle" onClick={() => setSidebar((v) => !v)}><PanelLeftClose size={19} /></button><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div></div><div className="topbar-actions"><div className="topbar-date"><CalendarDays size={15} /><span>{new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}</span></div><button className="icon-button" title="Open the guest homepage" aria-label="Guest homepage" onClick={() => window.location.assign('/home')}><Globe size={18} /></button><NotificationBell /><div className="avatar avatar-top">{user.first_name[0]}{user.last_name[0]}</div></div></header><main className="content"><Routes><Route path="/" element={<DashboardPage user={user} />} /><Route path="/dashboard" element={<DashboardPage user={user} />} /><Route path="/reservations" element={<ReservationsPage />} /><Route path="/guests" element={<GuestsPage />} /><Route path="/rooms" element={<RoomsPage />} /><Route path="/housekeeping" element={<HousekeepingPage />} /><Route path="/maintenance" element={<MaintenancePage />} /><Route path="/services" element={<ServicesPage />} /><Route path="/finance" element={<FinancePage />} /><Route path="/reports" element={<ReportsPage />} /><Route path="/settings" element={<SettingsPage />} /><Route path="*" element={<DashboardPage user={user} />} /></Routes></main></div><ToastHost /></div>
}

function NavSection({ label, items, onNavigate }: { label: string; items: NavItem[]; onNavigate: () => void }) { return <div className="nav-section"><span className="nav-label">{label}</span>{items.map(({ label: itemLabel, icon: Icon, to }) => <NavLink key={to} to={to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={onNavigate}><Icon size={17} /><span>{itemLabel}</span></NavLink>)}</div> }

function PageHeader({ eyebrow, title, subtitle, action, actionLabel, onAction }: { eyebrow?: string; title: string; subtitle?: string; action?: boolean; actionLabel?: string; onAction?: () => void }) { return <div className="page-header"><div><span className="eyebrow">{eyebrow ?? 'AURORA GRAND'}</span><h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}</div>{action && <button className="primary-button" onClick={onAction}><Plus size={17} />{actionLabel}</button>}</div> }

function StatCard({ label, value, detail, icon: Icon, tone, trend }: { label: string; value: string; detail: string; icon: React.ElementType; tone: string; trend?: 'up' | 'down' }) { return <div className="stat-card"><div className="stat-card-top"><span className={`stat-icon ${tone}`}><Icon size={18} /></span>{trend && <span className={`trend ${trend}`} >{trend === 'up' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />} 8.4%</span>}</div><div className="stat-value">{value}</div><div className="stat-label">{label}</div><div className="stat-detail">{detail}</div></div> }

function DashboardPage({ user }: { user?: User | null }) {
  const [data, setData] = useState<Dashboard | null>(null); const [error, setError] = useState('')
  useEffect(() => { api<Dashboard>('/dashboard').then(setData).catch((e) => setError(e.message)) }, [])
  if (error) return <ErrorState message={error} />
  if (!data) return <PageSkeleton />
  const s = data.stats
  const now = new Date()
  const greeting = now.getHours() < 12 ? 'Good morning' : now.getHours() < 18 ? 'Good afternoon' : 'Good evening'
  return <><PageHeader eyebrow={now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase()} title={`${greeting}, ${user?.first_name ?? 'there'}`} subtitle="Here’s the operational picture for Aurora Grand today." action actionLabel="New reservation" onAction={() => window.location.assign('/reservations')} /><div className="stat-grid"><StatCard label="Occupancy rate" value={`${s.occupancy_rate}%`} detail={`${s.occupied_rooms} of ${s.total_rooms} rooms occupied`} icon={Hotel} tone="teal" trend="up" /><StatCard label="Today's revenue" value={`$${money(s.today_revenue)}`} detail={`$${money(s.month_revenue)} this month`} icon={CircleDollarSign} tone="gold" trend="up" /><StatCard label="Arrivals today" value={String(s.today_check_ins).padStart(2, '0')} detail={`${s.today_check_outs} departures scheduled`} icon={CalendarDays} tone="blue" /><StatCard label="Housekeeping queue" value={String(s.pending_housekeeping).padStart(2, '0')} detail="Tasks need attention" icon={Sparkles} tone="coral" /></div><div className="dashboard-grid"><section className="panel revenue-panel"><PanelTitle title="Revenue overview" meta="Last 14 days" action="View report" href="/reports" /><div className="chart-wrap"><ResponsiveContainer width="100%" height={235}><AreaChart data={data.revenue_trend}><defs><linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2c8c7b" stopOpacity={0.24} /><stop offset="100%" stopColor="#2c8c7b" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e8edf1" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} interval={2} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} tickFormatter={(v) => `$${v}`} width={46} /><Tooltip contentStyle={{ border: '1px solid #d9e2ec', borderRadius: 8, boxShadow: '0 8px 24px rgba(16,42,67,.1)' }} formatter={(value) => [`$${money(String(value))}`, 'Revenue']} /><Area type="monotone" dataKey="value" stroke="#2c8c7b" strokeWidth={2.5} fill="url(#revFill)" /></AreaChart></ResponsiveContainer></div></section><section className="panel rooms-panel"><PanelTitle title="Room utilization" meta="Live status" action="View rooms" href="/rooms" /><div className="utilization"><div className="donut"><ResponsiveContainer width="100%" height={170}><PieChart><Pie data={[{ name: 'Occupied', value: s.occupied_rooms }, { name: 'Available', value: s.available_rooms }, { name: 'Reserved', value: s.reserved_rooms }, { name: 'Other', value: s.cleaning_rooms + s.maintenance_rooms }]} innerRadius={57} outerRadius={73} paddingAngle={3} dataKey="value" stroke="none"><Cell fill="#2c8c7b" /><Cell fill="#dce8e7" /><Cell fill="#e5b567" /><Cell fill="#e8c4bb" /></Pie></PieChart></ResponsiveContainer><div className="donut-center"><strong>{s.total_rooms}</strong><span>rooms</span></div></div><div className="legend"><LegendLine color="#2c8c7b" label="Occupied" value={s.occupied_rooms} /><LegendLine color="#dce8e7" label="Available" value={s.available_rooms} /><LegendLine color="#e5b567" label="Reserved" value={s.reserved_rooms} /><LegendLine color="#e8c4bb" label="Cleaning / OOS" value={s.cleaning_rooms + s.maintenance_rooms} /></div></div></section><section className="panel arrivals-panel"><PanelTitle title="Today at a glance" meta="Front desk" action="Open reservations" href="/reservations" /><div className="arrival-list"><ArrivalMetric icon={ArrowDownRight} label="Arrivals" value={s.today_check_ins} tone="teal" /><ArrivalMetric icon={ArrowUpRight} label="Departures" value={s.today_check_outs} tone="blue" /><ArrivalMetric icon={Users} label="In-house guests" value={s.current_guests} tone="gold" /><ArrivalMetric icon={Receipt} label="Outstanding" value={`$${money(s.outstanding_payments)}`} tone="coral" /></div></section><section className="panel activity-panel"><PanelTitle title="Upcoming arrivals" meta="Next 7 days" action="See calendar" href="/reservations" />{data.upcoming_arrivals.length === 0 ? <EmptyState icon={CalendarDays} title="No upcoming arrivals" copy="The calendar is clear for the next seven days." /> : <div className="mini-table">{data.upcoming_arrivals.slice(0, 4).map((r) => <div className="mini-row" key={r.id}><div className="date-block"><strong>{new Date(r.check_in_date).toLocaleDateString('en-US', { day: '2-digit' })}</strong><span>{new Date(r.check_in_date).toLocaleDateString('en-US', { month: 'short' })}</span></div><div className="mini-main"><strong>{r.guest.full_name}</strong><span>{r.room_type.name} · {r.nights} nights</span></div><span className={`status-pill ${r.status}`}>{pretty(r.status)}</span></div>)}</div>}</section></div></>
}

function PanelTitle({ title, meta, action, href }: { title: string; meta?: string; action?: string; href?: string }) { return <div className="panel-title"><div><h3>{title}</h3>{meta && <span>{meta}</span>}</div>{action && <a href={href}>{action}<ChevronRight size={14} /></a>}</div> }
function LegendLine({ color, label, value }: { color: string; label: string; value: number }) { return <div className="legend-line"><i style={{ background: color }} /><span>{label}</span><strong>{value}</strong></div> }
function ArrivalMetric({ icon: Icon, label, value, tone }: { icon: React.ElementType; label: string; value: number | string; tone: string }) { return <div className="arrival-metric"><span className={`metric-icon ${tone}`}><Icon size={16} /></span><div><strong>{value}</strong><span>{label}</span></div></div> }

const stayViews: { key: 'all' | 'arrivals' | 'in_house' | 'departures'; label: string }[] = [{ key: 'all', label: 'All stays' }, { key: 'arrivals', label: 'Arrivals' }, { key: 'in_house', label: 'In-house' }, { key: 'departures', label: 'Departures' }]

function ReservationsPage() {
  const [data, setData] = useState<Page<Reservation> | null>(null); const [search, setSearch] = useState(''); const [view, setView] = useState<'all' | 'arrivals' | 'in_house' | 'departures'>('all'); const [show, setShow] = useState(false); const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null)
  const load = useCallback(() => api<Page<Reservation>>(`/reservations?page_size=20${view !== 'all' ? `&view=${view}` : ''}${search ? `&search=${encodeURIComponent(search)}` : ''}`).then(setData).catch(() => setData({ items: [], total: 0, page: 1, page_size: 20, pages: 0, has_next: false, has_previous: false })), [search, view])
  useEffect(() => { load() }, [load])
  const { busyId, act } = useRowActions(load)
  const checkIn = (r: Reservation) => act(r.id, () => api(`/reservations/${r.id}/check-in`, { method: 'POST', body: JSON.stringify({}) }), `${r.reference} checked in`)
  const checkOut = (r: Reservation) => act(r.id, () => api(`/reservations/${r.id}/check-out`, { method: 'POST', body: JSON.stringify(Number(r.balance) > 0 ? { payment_amount: Number(r.balance), payment_method: 'cash' } : {}) }), `${r.reference} checked out`)
  const noShow = (r: Reservation) => act(r.id, () => api(`/reservations/${r.id}/no-show`, { method: 'POST' }), `${r.reference} marked as no-show`)
  const copyRef = (r: Reservation) => navigator.clipboard?.writeText(r.reference).then(() => toast(`${r.reference} copied`)).catch(() => toast('Could not copy the reference.', 'err'))
  return <><PageHeader eyebrow="FRONT OFFICE" title="Reservations" subtitle="Manage the stay lifecycle from booking to departure." action actionLabel="New reservation" onAction={() => setShow(true)} />{show && <ReservationModal onClose={() => setShow(false)} onSaved={() => { setShow(false); load() }} />}{cancelTarget && <ConfirmModal title={`Cancel ${cancelTarget.reference}`} subtitle="The room is released and the folio closed. This is recorded in the audit log." confirmLabel="Cancel stay" requireReason onConfirm={(reason) => act(cancelTarget.id, () => api(`/reservations/${cancelTarget.id}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) }), `${cancelTarget.reference} cancelled`)} onClose={() => setCancelTarget(null)} />}<div className="toolbar"><div className="search-box"><Search size={16} /><input placeholder="Search reservation or guest" value={search} onChange={(e) => setSearch(e.target.value)} /></div><div className="filter-group">{stayViews.map((v) => <button key={v.key} className={`filter-button ${view === v.key ? 'active' : ''}`} onClick={() => setView(v.key)}>{v.label}</button>)}</div><RowMenu size={18} actions={[{ label: 'Refresh list', icon: RefreshCw, onClick: () => { load(); toast('Reservations refreshed') } }]} /></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Reservation</th><th>Guest</th><th>Stay</th><th>Room</th><th>Amount</th><th>Status</th><th /></tr></thead><tbody>{data?.items.map((r) => { const canArrive = r.status === 'pending' || r.status === 'confirmed'; return <tr key={r.id}><td><strong className="mono">{r.reference}</strong><small>{pretty(r.booking_source)}</small></td><td><div className="person-cell"><div className="avatar avatar-small">{r.guest.full_name.split(' ').map((x) => x[0]).join('').slice(0, 2)}</div><div><strong>{r.guest.full_name}</strong><small>{r.guest.email || 'No email on file'}</small></div></div></td><td><strong>{formatDate(r.check_in_date)}</strong><small>{formatDate(r.check_out_date)} · {r.nights} nights</small></td><td>{r.room ? <span className="room-number">Room {r.room.number}</span> : <span className="muted">Unassigned</span>}<small>{r.room_type.name}</small></td><td><strong>${money(r.total_amount)}</strong><small className={Number(r.balance) > 0 ? 'warning-text' : 'success-text'}>{Number(r.balance) > 0 ? `$${money(r.balance)} due` : 'Paid in full'}</small></td><td><span className={`status-pill ${r.status}`}>{pretty(r.status)}</span></td><td><RowMenu actions={[...(canArrive ? [{ label: 'Check in', icon: LogIn, disabled: busyId === r.id, onClick: () => checkIn(r) }] : []), ...(r.status === 'checked_in' ? [{ label: 'Check out', icon: LogOut, disabled: busyId === r.id, onClick: () => checkOut(r) }] : []), ...(canArrive ? [{ label: 'Mark no-show', icon: Ban, disabled: busyId === r.id, onClick: () => noShow(r) }, { label: 'Cancel stay', icon: X, danger: true, onClick: () => setCancelTarget(r) }] : []), { label: 'Copy reference', icon: Copy, onClick: () => copyRef(r) }]} /></td></tr> })}</tbody></table>{data?.items.length === 0 && <EmptyState icon={CalendarDays} title="No reservations found" copy="Try adjusting your search or create the first stay." />}</div><TableFooter total={data?.total ?? 0} /></section></>
}

function GuestsPage() {
  const [data, setData] = useState<Page<Guest> | null>(null); const [search, setSearch] = useState(''); const [show, setShow] = useState(false); const [editing, setEditing] = useState<Guest | null>(null); const [archiveTarget, setArchiveTarget] = useState<Guest | null>(null)
  const load = useCallback(() => api<Page<Guest>>(`/guests?page_size=20${search ? `&search=${encodeURIComponent(search)}` : ''}`).then(setData), [search]); useEffect(() => { load().catch(() => undefined) }, [load])
  const { busyId, act } = useRowActions(() => { load().catch(() => undefined) })
  const copyEmail = (g: Guest) => navigator.clipboard?.writeText(g.email ?? '').then(() => toast('Email address copied')).catch(() => toast('Nothing to copy for this guest.', 'err'))
  return <><PageHeader eyebrow="GUEST RELATIONS" title="Guests" subtitle="Profiles, preferences and stay history in one place." action actionLabel="Register guest" onAction={() => setShow(true)} />{show && <GuestModal onClose={() => setShow(false)} onSaved={() => { setShow(false); load().catch(() => undefined) }} />}{editing && <GuestModal initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load().catch(() => undefined) }} />}{archiveTarget && <ConfirmModal title={`Archive ${archiveTarget.full_name}`} subtitle="The profile is soft-deleted and hidden from search. Existing stays and folios are preserved." confirmLabel="Archive guest" onConfirm={() => act(archiveTarget.id, () => api(`/guests/${archiveTarget.id}`, { method: 'DELETE' }), `${archiveTarget.full_name} archived`)} onClose={() => setArchiveTarget(null)} />}<div className="toolbar"><div className="search-box"><Search size={16} /><input placeholder="Search by name, email or reference" value={search} onChange={(e) => setSearch(e.target.value)} /></div><button className="filter-button active">All guests</button><button className="filter-button">VIP guests</button></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Guest</th><th>Contact</th><th>Nationality</th><th>Stays</th><th>Total spend</th><th>Balance</th><th /></tr></thead><tbody>{data?.items.map((g) => <tr key={g.id}><td><div className="person-cell"><div className={`avatar avatar-small ${g.is_vip ? 'vip' : ''}`}>{g.full_name.split(' ').map((x) => x[0]).join('').slice(0, 2)}</div><div><strong>{g.full_name} {g.is_vip && <span className="vip-star">✦</span>}</strong><small className="mono">{g.reference}</small></div></div></td><td><strong>{g.email || '—'}</strong><small>{g.phone || 'No phone on file'}</small></td><td>{g.nationality || '—'}</td><td><strong>{g.total_stays}</strong><small>{g.total_stays === 1 ? 'stay' : 'stays'}</small></td><td><strong>${money(g.total_spend)}</strong><small>Lifetime value</small></td><td><strong className={Number(g.outstanding_balance) > 0 ? 'warning-text' : 'success-text'}>{Number(g.outstanding_balance) ? `$${money(g.outstanding_balance)}` : 'Clear'}</strong></td><td><RowMenu actions={[{ label: 'Edit profile', icon: Pencil, onClick: () => setEditing(g) }, { label: 'Copy email', icon: Copy, disabled: !g.email, onClick: () => copyEmail(g) }, { label: 'Archive guest', icon: Archive, danger: true, disabled: busyId === g.id, onClick: () => setArchiveTarget(g) }]} /></td></tr>)}</tbody></table>{data?.items.length === 0 && <EmptyState icon={Users} title="No guests found" copy="Register a guest to begin building their stay history." />}</div><TableFooter total={data?.total ?? 0} /></section></>
}

function RoomsPage() { const [data, setData] = useState<Page<Room> | null>(null); const [filter, setFilter] = useState('all')
  const load = useCallback(() => api<Page<Room>>(`/rooms?page_size=50${filter !== 'all' ? `&status=${filter}` : ''}`).then(setData).catch(() => undefined), [filter])
  useEffect(() => { load() }, [load])
  const { busyId, act } = useRowActions(load)
  const setStatus = (room: Room, status: string) => act(room.id, () => api(`/rooms/${room.id}`, { method: 'PATCH', body: JSON.stringify({ status, price_per_night: Number(room.price_per_night) }) }), `Room ${room.number} marked ${pretty(status).toLowerCase()}`)
  return <><PageHeader eyebrow="PROPERTY" title="Rooms & rates" subtitle="Live room inventory, condition and availability." action actionLabel="Add room" /><div className="room-summary"><div><span className="summary-label">Total inventory</span><strong>{data?.total ?? '—'} <small>rooms</small></strong></div><div><span className="room-dot available" /><span>Available</span><strong>{data?.items.filter((r) => r.status === 'available').length ?? 0}</strong></div><div><span className="room-dot occupied" /><span>Occupied</span><strong>{data?.items.filter((r) => r.status === 'occupied').length ?? 0}</strong></div><div><span className="room-dot reserved" /><span>Reserved</span><strong>{data?.items.filter((r) => r.status === 'reserved').length ?? 0}</strong></div><div><span className="room-dot cleaning" /><span>Cleaning</span><strong>{data?.items.filter((r) => r.status === 'cleaning').length ?? 0}</strong></div></div><div className="toolbar"><div className="filter-group"><button className={`filter-button ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All rooms</button>{['available', 'occupied', 'reserved', 'cleaning', 'maintenance'].map((status) => <button key={status} className={`filter-button ${filter === status ? 'active' : ''}`} onClick={() => setFilter(status)}>{pretty(status)}</button>)}</div><button className="secondary-button"><CalendarDays size={16} />Availability calendar</button></div><div className="room-grid">{data?.items.map((room) => <div className="room-card" key={room.id}><div className={`room-card-top ${room.status}`}><span className="room-floor">FLOOR {room.floor}</span><span className={`status-pill ${room.status}`}>{pretty(room.status)}</span><span className="room-watermark">{room.number}</span></div><div className="room-card-body"><div className="room-title"><div><strong>Room {room.number}</strong><span>{room.room_type.name}</span></div><RowMenu size={16} actions={[...(room.status !== 'available' ? [{ label: 'Mark available', icon: Check, disabled: busyId === room.id, onClick: () => setStatus(room, 'available') }] : []), ...(room.status !== 'cleaning' ? [{ label: 'Send to cleaning', icon: Sparkles, disabled: busyId === room.id, onClick: () => setStatus(room, 'cleaning') }] : []), ...(room.status !== 'maintenance' ? [{ label: 'Flag maintenance', icon: Wrench, disabled: busyId === room.id, onClick: () => setStatus(room, 'maintenance') }] : []), ...(room.status !== 'out_of_service' ? [{ label: 'Take out of service', icon: Ban, danger: true, disabled: busyId === room.id, onClick: () => setStatus(room, 'out_of_service') }] : []), { label: 'Copy room number', icon: Copy, onClick: () => navigator.clipboard?.writeText(room.number).then(() => toast(`Room ${room.number} copied`)).catch(() => toast('Could not copy.', 'err')) }]} /></div><div className="room-specs"><span><BedDouble size={14} />{pretty(room.room_type.bed_type)}</span><span><Users size={14} />{room.capacity} guests</span><strong>${money(room.price_per_night)}<small>/night</small></strong></div></div></div>)}</div></> }

function HousekeepingPage() { const [data, setData] = useState<Page<Task> | null>(null)
  const load = useCallback(() => api<Page<Task>>('/housekeeping?page_size=50').then(setData).catch(() => undefined), [])
  useEffect(() => { load() }, [load])
  const { busyId, act } = useRowActions(load)
  const patch = (task: Task, body: Record<string, unknown>, message: string) => act(task.id, () => api(`/housekeeping/${task.id}`, { method: 'PATCH', body: JSON.stringify(body) }), message)
  const grouped = ['pending', 'in_progress', 'completed']; return <><PageHeader eyebrow="ROOMS DIVISION" title="Housekeeping" subtitle="Keep room readiness visible from the floor to the front desk." action actionLabel="Assign task" /><div className="ops-strip"><span><i className="room-dot dirty" />{data?.items.filter((t) => t.status === 'pending').length ?? 0} pending</span><span><i className="room-dot cleaning" />{data?.items.filter((t) => t.status === 'in_progress').length ?? 0} in progress</span><span><i className="room-dot available" />{data?.items.filter((t) => t.status === 'completed').length ?? 0} completed today</span><span className="ops-spacer" /><span className="muted">Today · {new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span></div><div className="kanban">{grouped.map((status) => <section className="kanban-column" key={status}><div className="kanban-head"><span>{pretty(status)}</span><b>{data?.items.filter((t) => t.status === status).length ?? 0}</b></div>{data?.items.filter((t) => t.status === status).map((task) => <div className="task-card" key={task.id}><div className="task-card-head"><strong>Room {task.room?.number ?? '—'}</strong><span className={`priority ${task.priority}`}>{pretty(task.priority)}</span></div><span className="task-type">{pretty(task.task_type)}</span><div className="task-card-foot"><span className="avatar avatar-tiny">SP</span><span>Sofia Patel</span><RowMenu size={16} actions={[...(task.status === 'pending' ? [{ label: 'Start cleaning', icon: Play, disabled: busyId === task.id, onClick: () => patch(task, { status: 'in_progress' }, `Room ${task.room?.number ?? ''} cleaning started`) }] : []), ...(task.status !== 'completed' ? [{ label: 'Mark completed', icon: Check, disabled: busyId === task.id, onClick: () => patch(task, { status: 'completed' }, `Room ${task.room?.number ?? ''} marked clean`) }] : []), { label: 'Set high priority', icon: AlertTriangle, disabled: busyId === task.id || task.priority === 'high', onClick: () => patch(task, { priority: 'high' }, 'Priority raised to high') }]} /></div></div>)}{data?.items.filter((t) => t.status === status).length === 0 && <div className="column-empty"><Check size={18} /><span>All clear</span></div>}</section>)}</div></> }

function MaintenancePage() { const [data, setData] = useState<Page<Ticket> | null>(null)
  const load = useCallback(() => api<Page<Ticket>>('/maintenance?page_size=30').then(setData).catch(() => undefined), [])
  useEffect(() => { load() }, [load])
  const { busyId, act } = useRowActions(load)
  const patch = (ticket: Ticket, body: Record<string, unknown>, message: string) => act(ticket.id, () => api(`/maintenance/${ticket.id}`, { method: 'PATCH', body: JSON.stringify(body) }), message)
  return <><PageHeader eyebrow="ENGINEERING" title="Maintenance" subtitle="Resolve issues before they become guest experiences." action actionLabel="Report issue" /><div className="maintenance-callout"><div className="callout-icon"><Wrench size={18} /></div><div><strong>{data?.total ?? 0} open maintenance tickets</strong><span>Prioritized by impact to guest rooms and shared spaces.</span></div><ChevronRight size={17} /></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Ticket</th><th>Issue</th><th>Location</th><th>Priority</th><th>Status</th><th>Reported</th><th /></tr></thead><tbody>{data?.items.map((t) => <tr key={t.id}><td><strong className="mono">{t.ticket_number}</strong></td><td><strong>{t.title}</strong><small>{t.category.replaceAll('_', ' ')}</small></td><td>{t.room_id ? 'Guest room' : 'Public area'}</td><td><span className={`priority ${t.priority}`}>{pretty(t.priority)}</span></td><td><span className={`status-pill ${t.status}`}>{pretty(t.status)}</span></td><td>{formatDate(t.reported_at)}</td><td><RowMenu actions={[...((t.status === 'open' || t.status === 'assigned') ? [{ label: 'Start work', icon: Play, disabled: busyId === t.id, onClick: () => patch(t, { status: 'in_progress' }, `${t.ticket_number} in progress`) }] : []), ...(t.status !== 'resolved' && t.status !== 'closed' ? [{ label: 'Mark resolved', icon: Check, disabled: busyId === t.id, onClick: () => patch(t, { status: 'resolved' }, `${t.ticket_number} resolved`) }] : []), ...(t.status === 'resolved' ? [{ label: 'Close ticket', icon: ClipboardCheck, disabled: busyId === t.id, onClick: () => patch(t, { status: 'closed' }, `${t.ticket_number} closed`) }] : []), { label: 'Set urgent priority', icon: AlertTriangle, disabled: busyId === t.id || t.priority === 'high', onClick: () => patch(t, { priority: 'high' }, `${t.ticket_number} set to urgent`) }]} /></td></tr>)}</tbody></table>{data?.items.length === 0 && <EmptyState icon={Wrench} title="No open tickets" copy="The property is looking good." />}</div></section></> }

function ServicesPage() { const [data, setData] = useState<Page<Service> | null>(null)
  const load = useCallback(() => api<Page<Service>>('/services?page_size=30').then(setData).catch(() => undefined), [])
  useEffect(() => { load() }, [load])
  const { busyId, act } = useRowActions(load)
  const toggle = (s: Service) => act(s.id, () => api(`/services/${s.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !s.is_active }) }), s.is_active ? `${s.name} deactivated` : `${s.name} activated`)
  return <><PageHeader eyebrow="GUEST EXPERIENCE" title="Services & dining" subtitle="The extras that turn a stay into a return visit." action actionLabel="Add service" /><div className="service-grid">{data?.items.map((s, i) => <div className="service-card" key={s.id}><div className={`service-illustration illustration-${i % 4}`}>{i % 4 === 0 ? <Sparkles /> : i % 4 === 1 ? <Coffee /> : i % 4 === 2 ? <Activity /> : <CarIcon />}</div><div className="service-card-content"><div className="service-card-top"><span>{pretty(s.category)}</span><RowMenu size={16} actions={[{ label: s.is_active ? 'Deactivate service' : 'Activate service', icon: s.is_active ? EyeOff : Eye, disabled: busyId === s.id, onClick: () => toggle(s) }, { label: 'Copy service code', icon: Copy, onClick: () => navigator.clipboard?.writeText(s.code).then(() => toast(`${s.code} copied`)).catch(() => toast('Could not copy.', 'err')) }]} /></div><h3>{s.name}</h3><p>{s.unit}</p><div><strong>${money(s.price)}</strong><small> + {s.tax_rate}% tax</small></div></div></div>)}</div></> }
function CarIcon() { return <span className="car-icon">↗</span> }

function FinancePage() {
  const [data, setData] = useState<Page<Payment> | null>(null); const [search, setSearch] = useState(''); const [entry, setEntry] = useState<'all' | 'payment' | 'refund'>('all'); const [show, setShow] = useState(false); const [refundTarget, setRefundTarget] = useState<Payment | null>(null); const [outstanding, setOutstanding] = useState<number | null>(null)
  const load = useCallback(() => api<Page<Payment>>(`/payments?page_size=50${entry !== 'all' ? `&entry=${entry}` : ''}${search ? `&search=${encodeURIComponent(search)}` : ''}`).then(setData).catch(() => undefined), [entry, search])
  useEffect(() => { load() }, [load])
  useEffect(() => { api<Page<Reservation>>('/reservations?page_size=200').then((page) => setOutstanding(page.items.reduce((sum, r) => sum + Number(r.balance), 0))).catch(() => undefined) }, [])
  const now = new Date()
  const collected = (data?.items ?? []).filter((p) => p.entry_type === 'payment' && p.status === 'paid' && new Date(p.paid_at).getMonth() === now.getMonth() && new Date(p.paid_at).getFullYear() === now.getFullYear()).reduce((sum, p) => sum + Number(p.amount), 0)
  const paidCount = (data?.items ?? []).filter((p) => p.status === 'paid').length
  const successRate = data && data.items.length > 0 ? Math.round((paidCount / data.items.length) * 1000) / 10 : null
  const exportCsv = () => {
    if (!data || data.items.length === 0) { toast('Nothing to export yet.', 'err'); return }
    downloadCsv(`payments-${now.toISOString().slice(0, 10)}.csv`, [['Number', 'Entry', 'Method', 'Amount', 'Currency', 'Status', 'Paid at', 'Reference'], ...data.items.map((p) => [p.number, p.entry_type, p.method_label, Number(p.amount), p.currency, p.status, p.paid_at, p.reference ?? ''])])
    toast(`${data.items.length} payment entries exported`)
  }
  return <><PageHeader eyebrow="FINANCE" title="Payments" subtitle="A clean, auditable view of every money movement." action actionLabel="Record payment" onAction={() => setShow(true)} />{show && <PaymentModal onClose={() => setShow(false)} onSaved={() => { setShow(false); load(); toast('Payment recorded') }} />}{refundTarget && <RefundModal payment={refundTarget} onClose={() => setRefundTarget(null)} onDone={(message) => { setRefundTarget(null); load(); toast(message) }} />}<div className="finance-summary"><div><span>Total collected this month</span><strong>${money(collected)}</strong><small className="success-text"><ArrowUpRight size={14} /> Live from the ledger</small></div><div><span>Outstanding balances</span><strong>{outstanding === null ? '—' : `$${money(outstanding)}`}</strong><small>Across active stays</small></div><div><span>Payment success rate</span><strong>{successRate === null ? '—' : `${successRate}%`}</strong><small>Current page of entries</small></div></div><div className="toolbar"><div className="search-box"><Search size={16} /><input placeholder="Search payment number" value={search} onChange={(e) => setSearch(e.target.value)} /></div><div className="filter-group"><button className={`filter-button ${entry === 'all' ? 'active' : ''}`} onClick={() => setEntry('all')}>All entries</button><button className={`filter-button ${entry === 'payment' ? 'active' : ''}`} onClick={() => setEntry('payment')}>Charges</button><button className={`filter-button ${entry === 'refund' ? 'active' : ''}`} onClick={() => setEntry('refund')}>Refunds</button></div><button className="secondary-button" onClick={exportCsv}><FileText size={16} />Export CSV</button></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Payment</th><th>Reservation</th><th>Method</th><th>Date</th><th>Amount</th><th>Status</th><th /></tr></thead><tbody>{data?.items.map((p) => <tr key={p.id}><td><strong className="mono">{p.number}</strong><small>{p.entry_type === 'refund' ? 'Refund' : 'Charge'}</small></td><td><strong>Reservation folio</strong><small className="mono">{p.id.slice(0, 8).toUpperCase()}</small></td><td><span className="method"><span className="method-dot" />{p.method_label}</span></td><td>{formatDate(p.paid_at)}</td><td><strong className={p.entry_type === 'refund' ? 'warning-text' : ''}>{p.entry_type === 'refund' ? '−' : ''}${money(p.amount)}</strong></td><td><span className="status-pill paid">{pretty(p.status)}</span></td><td><RowMenu actions={[...(p.entry_type === 'payment' && p.status === 'paid' ? [{ label: 'Issue refund', icon: Receipt, danger: true, onClick: () => setRefundTarget(p) }] : []), { label: 'Copy payment number', icon: Copy, onClick: () => navigator.clipboard?.writeText(p.number).then(() => toast(`${p.number} copied`)).catch(() => toast('Could not copy.', 'err')) }]} /></td></tr>)}</tbody></table>{data?.items.length === 0 && <EmptyState icon={CircleDollarSign} title="No payments yet" copy="Payments will appear here when a guest settles their folio." />}</div><TableFooter total={data?.total ?? 0} /></section></>
}

function PaymentModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [reservations, setReservations] = useState<Reservation[]>([]); const [reservationId, setReservationId] = useState(''); const [amount, setAmount] = useState(''); const [methods, setMethods] = useState<{ code: string; name: string }[]>([{ code: 'cash', name: 'Cash' }, { code: 'card', name: 'Card' }, { code: 'bank_transfer', name: 'Bank transfer' }, { code: 'mobile_money', name: 'Mobile money' }, { code: 'other', name: 'Other' }]); const [method, setMethod] = useState('cash'); const [reference, setReference] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  useEffect(() => { api<Page<Reservation>>('/reservations?page_size=200').then((page) => setReservations(page.items.filter((r) => Number(r.balance) > 0 && r.status !== 'cancelled' && r.status !== 'no_show' && r.status !== 'checked_out'))).catch((e) => setError(e instanceof Error ? e.message : 'Unable to load reservations')) }, [])
  useEffect(() => { api<PayMethod[]>('/admin/payment-methods').then((m) => { const active = m.filter((x) => x.is_active); if (active.length > 0) { setMethods(active.map((x) => ({ code: x.code, name: x.name }))); setMethod(active[0].code) } }).catch(() => undefined) }, [])
  function pick(id: string) { setReservationId(id); const r = reservations.find((x) => x.id === id); if (r) setAmount(String(r.balance)) }
  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!reservationId) { setError('Choose the reservation to settle.'); return }
    if (!(Number(amount) > 0)) { setError('Enter an amount greater than zero.'); return }
    setBusy(true)
    try { await api('/payments', { method: 'POST', body: JSON.stringify({ reservation_id: reservationId, amount: Number(amount), method, reference: reference || null }) }); onSaved() } catch (err) { setError(err instanceof Error ? err.message : 'Unable to record the payment') } finally { setBusy(false) }
  }
  return <Modal title="Record a payment" subtitle="Posts an immutable ledger entry against the reservation folio." onClose={onClose}><form className="modal-form" onSubmit={save}><label>Reservation with open balance<select value={reservationId} onChange={(e) => pick(e.target.value)} required><option value="">Select reservation</option>{reservations.map((r) => <option key={r.id} value={r.id}>{r.reference} · {r.guest.full_name} · ${money(r.balance)} due</option>)}</select></label><div className="form-two"><label>Amount<input type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label><label>Method<select value={method} onChange={(e) => setMethod(e.target.value)}>{methods.map((m) => <option key={m.code} value={m.code}>{m.name}</option>)}</select></label></div><label>Reference (optional)<input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Receipt or terminal reference" /></label>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label="Record payment" /></form></Modal>
}

function RefundModal({ payment, onClose, onDone }: { payment: Payment; onClose: () => void; onDone: (message: string) => void }) {
  const [amount, setAmount] = useState(String(payment.amount)); const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!(Number(amount) > 0)) { setError('Enter an amount greater than zero.'); return }
    if (reason.trim().length < 2) { setError('Please give a short reason.'); return }
    setBusy(true)
    try { await api(`/payments/${payment.id}/refund`, { method: 'POST', body: JSON.stringify({ amount: Number(amount), reason: reason.trim() }) }); onDone(`${payment.number} refunded`) } catch (err) { setError(err instanceof Error ? err.message : 'Unable to issue the refund') } finally { setBusy(false) }
  }
  return <Modal title={`Refund ${payment.number}`} subtitle={`Originally ${payment.method_label} · $${money(payment.amount)} · creates a separate refund ledger entry.`} onClose={onClose}><form className="modal-form" onSubmit={save}><div className="form-two"><label>Refund amount<input type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label><label>Original method<input value={payment.method_label} disabled /></label></div><label>Reason<textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="Recorded in the audit log" /></label>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label="Issue refund" /></form></Modal>
}

function downloadCsv(filename: string, rows: (string | number)[][]) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

type ReportPoint = { label: string; value: number | string; secondary?: number | string | null }
type ReportData = { name: string; generated_at: string; date_from: string; date_to: string; summary: Record<string, unknown>; series: ReportPoint[] }
type ReportTab = 'revenue' | 'occupancy' | 'reservations' | 'expenses' | 'housekeeping'
const REPORT_TABS: ReportTab[] = ['revenue', 'occupancy', 'reservations', 'expenses', 'housekeeping']
const REPORT_META: Record<ReportTab, { title: string; meta: string; color: string }> = {
  revenue: { title: 'Daily revenue', meta: 'USD · Paid charges only', color: '#2c8c7b' },
  occupancy: { title: 'Daily occupancy', meta: '% of bookable rooms occupied', color: '#2c8c7b' },
  reservations: { title: 'New reservations', meta: 'By booking date', color: '#5d84b2' },
  expenses: { title: 'Spend by category', meta: 'USD · All recorded expenses', color: '#d57f6b' },
  housekeeping: { title: 'Rooms cleaned', meta: 'Completed housekeeping tasks', color: '#e5b567' },
}
const MIX_COLORS = ['#2c8c7b', '#5d84b2', '#e5b567', '#d57f6b', '#9aa8b0', '#c48ac9']
function isoShift(daysBack: number) { const d = new Date(); d.setDate(d.getDate() - daysBack); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
function rnum(v: unknown) { return Number(v ?? 0) }
function reportKpis(tab: ReportTab, report: ReportData | null, days: number) {
  if (!report) return []
  const s = report.summary
  const best = report.series.reduce<ReportPoint | null>((acc, p) => (!acc || rnum(p.value) > rnum(acc.value) ? p : acc), null)
  switch (tab) {
    case 'revenue': { const total = rnum(s.total_revenue); return [
      { label: 'Total revenue', value: `$${money(String(total))}`, hint: `${rnum(s.payment_count)} days with payments` },
      { label: 'Average per day', value: `$${money(String(Math.round(total / days)))}`, hint: `Spread over ${days} days` },
      { label: 'Best day', value: best ? `$${money(String(rnum(best.value)))}` : '—', hint: best ? best.label : 'No payments in range' }] }
    case 'occupancy': { const peak = report.series.reduce<ReportPoint | null>((acc, p) => (!acc || rnum(p.value) > rnum(acc.value) ? p : acc), null); return [
      { label: 'Average occupancy', value: `${rnum(s.average_occupancy)}%`, hint: `Across ${rnum(s.rooms)} bookable rooms` },
      { label: 'Peak day', value: peak ? `${rnum(peak.value)}%` : '—', hint: peak ? peak.label : 'No stays in range' },
      { label: 'Room-nights sold', value: String(report.series.reduce((acc, p) => acc + rnum(p.secondary), 0)), hint: 'Occupied room-nights in range' }] }
    case 'reservations': { return [
      { label: 'New reservations', value: String(rnum(s.total_reservations)), hint: 'Booked inside this range' },
      { label: 'Room-nights', value: String(rnum(s.room_nights)), hint: 'Total nights sold' },
      { label: 'Booking value', value: `$${money(String(rnum(s.booking_value)))}`, hint: 'Folio totals for these bookings' }] }
    case 'expenses': { const total = rnum(s.total_expenses); const top = report.series[0]; return [
      { label: 'Total spend', value: `$${money(String(total))}`, hint: `${rnum(s.categories)} expense categories` },
      { label: 'Average per day', value: `$${money(String(Math.round(total / days)))}`, hint: `Spread over ${days} days` },
      { label: 'Largest category', value: top ? top.label : '—', hint: top ? `$${money(String(rnum(top.value)))}` : 'No expenses in range' }] }
    case 'housekeeping': { return [
      { label: 'Rooms cleaned', value: String(rnum(s.completed_in_range)), hint: 'Tasks completed in range' },
      { label: 'Inspected', value: String(rnum(s.inspected_in_range)), hint: 'Passed inspection in range' },
      { label: 'Open backlog', value: String(rnum(s.open_backlog)), hint: 'Pending or in progress right now' }] }
  }
}
function ReportChart({ tab, report, days }: { tab: ReportTab; report: ReportData; days: number }) {
  const meta = REPORT_META[tab]
  const data = report.series.map((p) => ({ label: tab === 'expenses' ? p.label : p.label.slice(5), full: p.label, value: rnum(p.value), secondary: rnum(p.secondary) }))
  const interval = Math.max(0, Math.ceil(data.length / 14) - 1)
  const tipStyle = { border: '1px solid #d9e2ec', borderRadius: 8, boxShadow: '0 8px 24px rgba(16,42,67,.1)' }
  const fmt = (value: number): [string, string] => tab === 'revenue' || tab === 'expenses' ? [`$${money(String(value))}`, tab === 'revenue' ? 'Revenue' : 'Spend'] : tab === 'occupancy' ? [`${value}%`, 'Occupancy'] : [String(value), tab === 'reservations' ? 'New reservations' : 'Rooms cleaned']
  if (tab === 'occupancy') return <ResponsiveContainer width="100%" height={300}><AreaChart data={data}><defs><linearGradient id="occFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2c8c7b" stopOpacity={0.24} /><stop offset="100%" stopColor="#2c8c7b" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e8edf1" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} interval={interval} /><YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} tickFormatter={(v) => `${v}%`} width={40} /><Tooltip contentStyle={tipStyle} labelFormatter={(_, payload) => (payload?.[0]?.payload as { full?: string })?.full ?? ''} formatter={(value) => fmt(Number(value))} /><Area type="monotone" dataKey="value" stroke={meta.color} strokeWidth={2.5} fill="url(#occFill)" /></AreaChart></ResponsiveContainer>
  return <ResponsiveContainer width="100%" height={300}><BarChart data={data}><CartesianGrid vertical={false} stroke="#e8edf1" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} interval={interval} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} tickFormatter={(v) => tab === 'revenue' || tab === 'expenses' ? `$${v}` : String(v)} width={tab === 'revenue' || tab === 'expenses' ? 52 : 34} /><Tooltip contentStyle={tipStyle} labelFormatter={(_, payload) => (payload?.[0]?.payload as { full?: string })?.full ?? ''} formatter={(value) => fmt(Number(value))} cursor={{ fill: 'rgba(44,140,123,.06)' }} /><Bar dataKey="value" fill={meta.color} radius={[3, 3, 0, 0]} maxBarSize={38} /></BarChart></ResponsiveContainer>
}
function ReportsPage() {
  const [tab, setTab] = useState<ReportTab>('revenue')
  const [from, setFrom] = useState(() => isoShift(29))
  const [to, setTo] = useState(() => isoShift(0))
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let stale = false
    setLoading(true)
    api<ReportData>(`/reports/${tab}?date_from=${from}&date_to=${to}`).then((r) => { if (!stale) { setReport(r); setLoading(false) } }).catch((e) => { if (!stale) { setReport(null); setLoading(false); toast(e instanceof Error ? e.message : 'Could not load the report.', 'err') } })
    return () => { stale = true }
  }, [tab, from, to])
  const days = useMemo(() => Math.max(1, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86400000) + 1), [from, to])
  const setRange = (n: number) => { setFrom(isoShift(n - 1)); setTo(isoShift(0)) }
  const meta = REPORT_META[tab]
  const kpis = reportKpis(tab, report, days)
  const mix = tab === 'reservations' && report ? ((report.summary.status_mix ?? []) as { label: string; value: number }[]) : []
  const exportReport = () => {
    if (!report) return
    const headers: Record<ReportTab, (string | number)[]> = { revenue: ['Date', 'Revenue USD'], occupancy: ['Date', 'Occupancy %', 'Rooms occupied'], reservations: ['Date', 'New reservations'], expenses: ['Category', 'Total USD'], housekeeping: ['Date', 'Rooms cleaned'] }
    downloadCsv(`${tab}-report-${report.date_from}-to-${report.date_to}.csv`, [headers[tab], ...report.series.map((p) => (tab === 'occupancy' ? [p.label, rnum(p.value), rnum(p.secondary)] : [p.label, rnum(p.value)]))])
    toast('Report exported as CSV')
  }
  const emptyCopy: Record<ReportTab, [string, string]> = { revenue: ['No revenue recorded', 'No paid charges landed in this date range.'], occupancy: ['No occupied rooms', 'No stayed reservations overlap this date range.'], reservations: ['No reservations booked', 'No bookings were created inside this date range.'], expenses: ['No expenses recorded', 'No spend was logged in this date range.'], housekeeping: ['No rooms cleaned', 'No housekeeping tasks were completed in this range.'] }
  return <><PageHeader eyebrow="INSIGHTS" title="Reports" subtitle="The signals behind confident operating decisions." />
    <div className="report-tabs">{REPORT_TABS.map((t) => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{pretty(t)}</button>)}</div>
    <div className="toolbar">
      <div className="report-range"><input type="date" value={from} max={to} onChange={(e) => e.target.value && setFrom(e.target.value)} aria-label="From date" /><span>to</span><input type="date" value={to} min={from} onChange={(e) => e.target.value && setTo(e.target.value)} aria-label="To date" /></div>
      <div className="filter-group">
        <button className={`filter-button ${from === isoShift(6) && to === isoShift(0) ? 'active' : ''}`} onClick={() => setRange(7)}>7 days</button>
        <button className={`filter-button ${from === isoShift(29) && to === isoShift(0) ? 'active' : ''}`} onClick={() => setRange(30)}>30 days</button>
        <button className={`filter-button ${from === isoShift(89) && to === isoShift(0) ? 'active' : ''}`} onClick={() => setRange(90)}>90 days</button>
      </div>
      <button className="secondary-button" onClick={exportReport} disabled={!report || report.series.length === 0}><FileText size={16} />Export CSV</button>
    </div>
    <div className="finance-summary">{kpis.map((k) => <div key={k.label}><span>{k.label}</span><strong>{k.value}</strong><small>{k.hint}</small></div>)}</div>
    <div className={tab === 'reservations' ? 'report-grid' : ''}>
      <section className="panel report-chart"><PanelTitle title={meta.title} meta={report ? `${meta.meta} · ${report.date_from} → ${report.date_to}` : meta.meta} />
        {loading ? <div className="report-loading"><RefreshCw size={16} className="spin" /><span>Crunching the numbers…</span></div> : !report || report.series.length === 0 ? <EmptyState icon={FileText} title={emptyCopy[tab][0]} copy={emptyCopy[tab][1]} /> : <ReportChart tab={tab} report={report} days={days} />}
      </section>
      {tab === 'reservations' && <section className="panel report-chart"><PanelTitle title="Status mix" meta="Bookings in range by status" />
        {mix.length === 0 ? <EmptyState icon={CalendarDays} title="No bookings to break down" copy="Book a reservation to see the status mix." /> : <><div className="donut" style={{ margin: '0 auto', width: 190 }}><ResponsiveContainer width="100%" height={185}><PieChart><Pie data={mix} innerRadius={58} outerRadius={78} paddingAngle={3} dataKey="value" nameKey="label" stroke="none">{mix.map((m, i) => <Cell key={m.label} fill={MIX_COLORS[i % MIX_COLORS.length]} />)}</Pie><Tooltip contentStyle={{ border: '1px solid #d9e2ec', borderRadius: 8 }} /></PieChart></ResponsiveContainer></div><div className="legend">{mix.map((m, i) => <LegendLine key={m.label} color={MIX_COLORS[i % MIX_COLORS.length]} label={m.label} value={m.value} />)}</div></>}
      </section>}
    </div>
  </>
}

type Setting = { key: string; value: string | null; value_type: string; group_name: string; label: string; editable: boolean; is_public: boolean }
type AdminUser = { id: string; email: string; username: string; full_name: string; job_title?: string | null; department?: string | null; status: string; is_superuser: boolean; roles: { code: string; name: string; level: number }[]; last_login_at?: string | null }
type RoleInfo = { id: string; code: string; name: string; level: number; is_system: boolean; is_active: boolean; permissions: { code: string }[] }
type PayMethod = { id: string; code: string; name: string; type: string; requires_reference: boolean; is_active: boolean }
type AuditRow = { id: string; username: string | null; action: string; resource: string; description: string | null; success: boolean; ip_address: string | null; created_at: string }

const settingsTabs = [{ key: 'profile', label: 'Hotel profile' }, { key: 'access', label: 'Access & roles' }, { key: 'billing', label: 'Billing' }, { key: 'audit', label: 'Audit trail' }] as const

function SettingsPage() {
  const [tab, setTab] = useState<(typeof settingsTabs)[number]['key']>('profile')
  return <><PageHeader eyebrow="ADMINISTRATION" title="Settings" subtitle="Configuration for the Aurora Grand workspace." /><div className="report-tabs">{settingsTabs.map((t) => <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>{t.label}</button>)}</div>{tab === 'profile' && <ProfileSettings />}{tab === 'access' && <AccessSettings />}{tab === 'billing' && <BillingSettings />}{tab === 'audit' && <AuditTrail />}</>
}

function ProfileSettings() {
  const [rows, setRows] = useState<Setting[] | null>(null); const [values, setValues] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false)
  const load = useCallback(() => api<Setting[]>('/admin/settings').then((r) => { setRows(r); setValues(Object.fromEntries(r.map((s) => [s.key, s.value ?? '']))) }).catch((e) => toast(e instanceof Error ? e.message : 'Unable to load settings', 'err')), [])
  useEffect(() => { load() }, [load])
  const fields = (rows ?? []).filter((s) => s.group_name === 'hotel' || s.group_name === 'operations')
  const changed = fields.filter((s) => s.editable && (values[s.key] ?? '') !== (s.value ?? ''))
  async function save() { setBusy(true); try { for (const s of changed) await api(`/admin/settings/${s.key}`, { method: 'PATCH', body: JSON.stringify({ value: values[s.key] }) }); toast('Hotel profile saved'); load() } catch (e) { toast(e instanceof Error ? e.message : 'Saving failed', 'err') } finally { setBusy(false) } }
  if (!rows) return <PageSkeleton />
  return <section className="panel settings-panel"><div className="settings-head"><div><h3>Hotel profile</h3><span>Property details, contact information and branding.</span></div>{changed.length > 0 && <button className="primary-button" disabled={busy} onClick={save}>{busy ? <span className="spinner" /> : <><Check size={16} />Save {changed.length} change{changed.length > 1 ? 's' : ''}</>}</button>}</div><div className="settings-form">{fields.map((s) => <label key={s.key} className={s.key === 'hotel_address' || s.key === 'hotel_tagline' ? 'full' : ''}>{s.label}<input value={values[s.key] ?? ''} disabled={!s.editable} onChange={(e) => setValues((v) => ({ ...v, [s.key]: e.target.value }))} /></label>)}</div></section>
}

function AccessSettings() {
  const [users, setUsers] = useState<Page<AdminUser> | null>(null); const [roles, setRoles] = useState<RoleInfo[]>([]); const [show, setShow] = useState(false); const [deactivate, setDeactivate] = useState<AdminUser | null>(null)
  const load = useCallback(() => { api<Page<AdminUser>>('/admin/users?page_size=50').then(setUsers).catch(() => undefined); api<Page<RoleInfo>>('/admin/roles?page_size=50').then((r) => setRoles(r.items)).catch(() => undefined) }, [])
  useEffect(() => { load() }, [load])
  const { act } = useRowActions(load)
  return <><div className="settings-toolbar"><div className="settings-toolbar-copy"><strong>Staff accounts</strong><span>{users?.total ?? '—'} people with workspace access</span></div><button className="primary-button" onClick={() => setShow(true)}><Plus size={16} />Add staff member</button></div>{show && <StaffModal roles={roles} onClose={() => setShow(false)} onSaved={() => { setShow(false); load(); toast('Staff account created') }} />}{deactivate && <ConfirmModal title={`Deactivate ${deactivate.full_name}`} subtitle="The account keeps its audit history but can no longer sign in." confirmLabel="Deactivate" onConfirm={() => act(deactivate.id, () => api(`/admin/users/${deactivate.id}/deactivate`, { method: 'POST' }), `${deactivate.full_name} deactivated`)} onClose={() => setDeactivate(null)} />}<section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Staff member</th><th>Role</th><th>Department</th><th>Last sign-in</th><th>Status</th><th /></tr></thead><tbody>{users?.items.map((u) => <tr key={u.id}><td><div className="person-cell"><div className="avatar avatar-small">{u.full_name.split(' ').map((x) => x[0]).join('').slice(0, 2)}</div><div><strong>{u.full_name}</strong><small>{u.email}</small></div></div></td><td>{u.roles.map((r) => r.name).join(', ') || (u.is_superuser ? 'Super administrator' : '—')}</td><td>{u.department ?? '—'}</td><td>{u.last_login_at ? formatDate(u.last_login_at) : 'Never'}</td><td><span className={`status-pill ${u.status === 'active' ? 'paid' : 'cancelled'}`}>{pretty(u.status)}</span></td><td><RowMenu actions={[...(u.status === 'active' ? [{ label: 'Deactivate account', icon: ShieldCheck, danger: true, disabled: u.is_superuser, onClick: () => setDeactivate(u) }] : [])]} /></td></tr>)}</tbody></table></div></section><section className="panel settings-panel roles-panel"><div className="settings-head"><div><h3>Roles & permission sets</h3><span>Built-in roles and the number of permissions each grants.</span></div></div><div className="role-chips">{roles.map((r) => <div key={r.id} className="role-chip"><strong>{r.name}</strong><span>{r.permissions.length} permissions · level {r.level}</span></div>)}</div></section></>
}

function StaffModal({ roles, onClose, onSaved }: { roles: RoleInfo[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', username: '', password: '', role: roles[0]?.code ?? 'receptionist' }); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function save(e: React.FormEvent) { e.preventDefault(); setBusy(true); try { await api('/admin/users', { method: 'POST', body: JSON.stringify({ first_name: form.first_name, last_name: form.last_name, email: form.email, username: form.username, password: form.password, role_codes: [form.role], must_change_password: true }) }); onSaved() } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create the account') } finally { setBusy(false) } }
  return <Modal title="Add a staff member" subtitle="They will be asked to choose their own password at first sign-in." onClose={onClose}><form className="modal-form" onSubmit={save}><div className="form-two"><label>First name<input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required /></label><label>Last name<input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required /></label></div><label>Work email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label><div className="form-two"><label>Username<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required /></label><label>Temporary password<input type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} minLength={8} required /></label></div><label>Role<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select></label>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label="Create account" /></form></Modal>
}

function BillingSettings() {
  const [rows, setRows] = useState<Setting[] | null>(null); const [values, setValues] = useState<Record<string, string>>({}); const [methods, setMethods] = useState<PayMethod[] | null>(null); const [busy, setBusy] = useState(false); const [toggling, setToggling] = useState('')
  const load = useCallback(() => { api<Setting[]>('/admin/settings').then((r) => { setRows(r); setValues(Object.fromEntries(r.map((s) => [s.key, s.value ?? '']))) }).catch(() => undefined); api<PayMethod[]>('/admin/payment-methods').then(setMethods).catch(() => undefined) }, [])
  useEffect(() => { load() }, [load])
  const fields = (rows ?? []).filter((s) => s.group_name === 'finance' && !s.key.startsWith('sequence_'))
  const sequences = (rows ?? []).filter((s) => s.key.startsWith('sequence_'))
  const changed = fields.filter((s) => s.editable && (values[s.key] ?? '') !== (s.value ?? ''))
  async function save() { setBusy(true); try { for (const s of changed) await api(`/admin/settings/${s.key}`, { method: 'PATCH', body: JSON.stringify({ value: values[s.key] }) }); toast('Billing configuration saved'); load() } catch (e) { toast(e instanceof Error ? e.message : 'Saving failed', 'err') } finally { setBusy(false) } }
  async function toggle(m: PayMethod) { setToggling(m.id); try { await api(`/admin/payment-methods/${m.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !m.is_active }) }); toast(m.is_active ? `${m.name} no longer offered at checkout` : `${m.name} accepted again`); load() } catch (e) { toast(e instanceof Error ? e.message : 'Update failed', 'err') } finally { setToggling('') } }
  if (!rows || !methods) return <PageSkeleton />
  return <><section className="panel settings-panel"><div className="settings-head"><div><h3>Taxes & currency</h3><span>Applied to accommodation and service charges.</span></div>{changed.length > 0 && <button className="primary-button" disabled={busy} onClick={save}>{busy ? <span className="spinner" /> : <><Check size={16} />Save changes</>}</button>}</div><div className="settings-form">{fields.map((s) => <label key={s.key}>{s.label}<input value={values[s.key] ?? ''} disabled={!s.editable} onChange={(e) => setValues((v) => ({ ...v, [s.key]: e.target.value }))} /></label>)}{sequences.map((s) => <label key={s.key}>{s.label}<input value={`${s.label}: next number ${s.value}`} disabled /></label>)}</div></section><section className="panel settings-panel"><div className="settings-head"><div><h3>Accepted payment methods</h3><span>Disabled methods are hidden from the record-payment form.</span></div></div><div className="method-list">{methods.map((m) => <div key={m.id} className="method-row"><div><strong>{m.name}</strong><span>{pretty(m.type)}{m.requires_reference ? ' · reference required' : ''}</span></div><button className={m.is_active ? 'filter-button active' : 'filter-button'} disabled={toggling === m.id} onClick={() => toggle(m)}>{m.is_active ? 'Accepted' : 'Disabled'}</button></div>)}</div></section></>
}

function AuditTrail() {
  const [items, setItems] = useState<AuditRow[]>([]); const [total, setTotal] = useState(0); const [search, setSearch] = useState(''); const [page, setPage] = useState(1); const [busy, setBusy] = useState(false)
  useEffect(() => { setPage(1) }, [search])
  useEffect(() => {
    let active = true
    setBusy(true)
    api<Page<AuditRow>>(`/admin/audit-logs?page_size=25&page=${page}${search ? `&search=${encodeURIComponent(search)}` : ''}`)
      .then((p) => { if (!active) return; setTotal(p.total); setItems((current) => (page === 1 ? p.items : [...current, ...p.items])) })
      .catch(() => undefined)
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [page, search])
  return <><div className="toolbar"><div className="search-box"><Search size={16} /><input placeholder="Search user, action or resource" value={search} onChange={(e) => setSearch(e.target.value)} /></div><span className="muted">{total} immutable entries</span></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>When</th><th>User</th><th>Action</th><th>Resource</th><th>IP address</th><th>Result</th></tr></thead><tbody>{items.map((a) => <tr key={a.id}><td><strong>{new Date(a.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</strong></td><td><strong>{a.username ?? 'system'}</strong></td><td><span className="mono">{a.action}</span></td><td>{pretty(a.resource)}{a.description ? <small> · {a.description}</small> : null}</td><td>{a.ip_address ?? '—'}</td><td><span className={`status-pill ${a.success ? 'paid' : 'cancelled'}`}>{a.success ? 'Success' : 'Failed'}</span></td></tr>)}</tbody></table>{items.length === 0 && <EmptyState icon={ClipboardCheck} title="No audit entries" copy="System activity will appear here as the workspace is used." />}</div>{items.length < total && <div className="table-footer"><span>Showing {items.length} of {total}</span><button className="secondary-button" disabled={busy} onClick={() => setPage((p) => p + 1)}>Load more</button></div>}</section></>
}

function GuestModal({ onClose, onSaved, initial }: { onClose: () => void; onSaved: () => void; initial?: Guest }) { const [form, setForm] = useState({ first_name: initial?.first_name ?? '', last_name: initial?.last_name ?? '', email: initial?.email ?? '', phone: initial?.phone ?? '', nationality: initial?.nationality ?? '' }); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); async function save(e: React.FormEvent) { e.preventDefault(); setBusy(true); const payload = { ...form, email: form.email || null, phone: form.phone || null, nationality: form.nationality || null }; try { if (initial) await api(`/guests/${initial.id}`, { method: 'PATCH', body: JSON.stringify(payload) }); else await api('/guests', { method: 'POST', body: JSON.stringify(payload) }); onSaved() } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save guest') } finally { setBusy(false) } } return <Modal title={initial ? `Edit ${initial.full_name}` : 'Register a guest'} subtitle={initial ? 'Update the guest profile; changes apply to future stays.' : 'Create a profile for a new guest or walk-in.'} onClose={onClose}><form className="modal-form" onSubmit={save}><div className="form-two"><label>First name<input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required /></label><label>Last name<input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required /></label></div><label>Email address<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label><div className="form-two"><label>Phone<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label><label>Nationality<input value={form.nationality} onChange={(e) => setForm({ ...form, nationality: e.target.value })} /></label></div>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label={initial ? 'Save changes' : 'Save guest'} /></form></Modal> }

function ReservationModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) { const [guests, setGuests] = useState<Guest[]>([]); const [types, setTypes] = useState<{ id: string; name: string }[]>([]); const [form, setForm] = useState({ guest_id: '', room_type_id: '', check_in_date: '', check_out_date: '', adults: 1 }); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); useEffect(() => { Promise.all([api<Page<Guest>>('/guests?page_size=100'), api<Page<{ id: string; name: string }>>('/room-types?page_size=100')]).then(([g, t]) => { setGuests(g.items); setTypes(t.items) }).catch((e) => setError(e.message)) }, []); async function save(e: React.FormEvent) { e.preventDefault(); setBusy(true); try { await api('/reservations', { method: 'POST', body: JSON.stringify({ ...form, adults: Number(form.adults) }) }); onSaved() } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create reservation') } finally { setBusy(false) } } return <Modal title="New reservation" subtitle="Secure a room and create the guest folio." onClose={onClose}><form className="modal-form" onSubmit={save}><label>Guest<select value={form.guest_id} onChange={(e) => setForm({ ...form, guest_id: e.target.value })} required><option value="">Select guest</option>{guests.map((g) => <option key={g.id} value={g.id}>{g.full_name} · {g.reference}</option>)}</select></label><label>Room type<select value={form.room_type_id} onChange={(e) => setForm({ ...form, room_type_id: e.target.value })} required><option value="">Select room type</option>{types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><div className="form-two"><label>Check-in<input type="date" value={form.check_in_date} onChange={(e) => setForm({ ...form, check_in_date: e.target.value })} required /></label><label>Check-out<input type="date" value={form.check_out_date} onChange={(e) => setForm({ ...form, check_out_date: e.target.value })} required /></label></div><label>Adults<input type="number" min="1" value={form.adults} onChange={(e) => setForm({ ...form, adults: Number(e.target.value) })} required /></label>{error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}<ModalActions onClose={onClose} busy={busy} label="Create reservation" /></form></Modal> }
function Modal({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: React.ReactNode }) { return <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><div className="modal"><div className="modal-head"><div><h2>{title}</h2><p>{subtitle}</p></div><button className="icon-button" onClick={onClose}><X size={18} /></button></div>{children}</div></div> }
function ModalActions({ onClose, busy, label = 'Save guest' }: { onClose: () => void; busy: boolean; label?: string }) { return <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy}>{busy ? <span className="spinner" /> : <><Check size={16} />{label}</>}</button></div> }
function EmptyState({ icon: Icon, title, copy }: { icon: React.ElementType; title: string; copy: string }) { return <div className="empty-state"><Icon size={24} /><strong>{title}</strong><span>{copy}</span></div> }
function ErrorState({ message }: { message: string }) { return <div className="page-error"><AlertTriangle size={22} /><h2>Something went wrong</h2><p>{message}</p><button className="secondary-button" onClick={() => window.location.reload()}>Try again</button></div> }
function PageSkeleton() { return <div className="skeleton-page"><div className="skeleton-line wide" /><div className="skeleton-line" /><div className="skeleton-grid">{[1, 2, 3, 4].map((i) => <div className="skeleton-card" key={i} />)}</div></div> }
function TableFooter({ total }: { total: number }) { return <div className="table-footer"><span>Showing {Math.min(total, 20)} of {total} records</span><div><button className="page-button" disabled>‹</button><button className="page-button active">1</button><button className="page-button" disabled>›</button></div></div> }
function formatDate(value: string) { return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }

export default App
