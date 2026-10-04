import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, Archive, ArrowDownRight, ArrowUpRight, Ban, BedDouble, Bell, CalendarDays, Check, ChevronRight, CircleDollarSign, ClipboardCheck, Coffee, Copy, Eye, EyeOff, FileText, Hotel, House, LayoutDashboard, LogIn, LogOut, Menu, Moon, MoreHorizontal, PanelLeftClose, Pencil, Play, Plus, Receipt, RefreshCw, Search, Settings, ShieldCheck, Sparkles, UserRound, Users, Wrench, X } from 'lucide-react'
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

function VisitorHome({ onStaffLogin }: { onStaffLogin: () => void }) {
  return <main className="visitor-home">
    <header className="visitor-nav"><div className="visitor-brand"><span className="brand-icon"><Hotel size={18} /></span><span>AURORA <b>GRAND</b></span></div><button className="secondary-button visitor-login" onClick={onStaffLogin}>Staff sign in <ChevronRight size={15} /></button></header>
    <section className="visitor-hero"><div className="visitor-hero-copy"><span className="eyebrow">AURORA GRAND HOTEL · HARBOR DISTRICT</span><h1>A quieter kind<br />of <em>luxury.</em></h1><p>Thoughtful rooms, warm service, and a stay shaped around the way you want to feel when you arrive.</p><div className="visitor-actions"><button className="primary-button" onClick={() => document.getElementById('visitor-features')?.scrollIntoView({ behavior: 'smooth' })}>Explore the hotel <ChevronRight size={16} /></button><button className="text-button" onClick={onStaffLogin}>Hotel staff sign in <ChevronRight size={15} /></button></div></div><div className="visitor-hero-card"><span className="visitor-card-kicker">THE AURORA EXPERIENCE</span><strong>Stay a little<br /><em>longer.</em></strong><span className="visitor-card-meta">Rooms · Dining · Wellness</span></div></section>
    <section className="visitor-intro"><div><span className="eyebrow">A PLACE TO ARRIVE</span><h2>Made for unhurried mornings and memorable evenings.</h2></div><p>From the first welcome to the final coffee, every detail at Aurora Grand is considered with care. Discover a modern landmark with the soul of a private residence.</p></section>
    <section id="visitor-features" className="visitor-features"><article><BedDouble size={20} /><span className="eyebrow">ROOMS & SUITES</span><h3>Rest beautifully</h3><p>Calm interiors, considered comforts, and views that make the city feel far away.</p></article><article><Coffee size={20} /><span className="eyebrow">DINING</span><h3>Gather well</h3><p>Seasonal plates and effortless service from breakfast through late evening.</p></article><article><Sparkles size={20} /><span className="eyebrow">WELLNESS</span><h3>Find your pace</h3><p>A quiet retreat for restorative treatments, movement, and time to yourself.</p></article></section>
    <footer className="visitor-footer"><span>© 2026 Aurora Grand Hotel</span><span>Harbor District · New York</span></footer>
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
  if (checking) return <div className="app-loading"><div className="brand-loader"><Hotel size={22} /><span>AURORA GRAND</span></div><span className="spinner dark" /></div>
  if (authError) return <ErrorState message={authError} />
  if (!user) {
    if (!autoSignInFailed && (authConfig === null || loginDisabled)) return <div className="app-loading"><div className="brand-loader"><Hotel size={22} /><span>AURORA GRAND</span></div><span className="muted">Sign-in is disabled — opening the test workspace…</span><span className="spinner dark" /></div>
    if (autoSignInFailed) return <Login onLogin={handleLogin} notice="The automatic test sign-in could not be completed. Use the development account button, or the seeded credentials from the README." />
    return location.pathname === '/' ? <VisitorHome onStaffLogin={() => navigate('/login')} /> : <Login onLogin={handleLogin} />
  }
  return <AppShell user={user} onLogout={handleLogout} testMode={loginDisabled} />
}

function AppShell({ user, onLogout, testMode = false }: { user: User; onLogout: () => void; testMode?: boolean }) {
  const [sidebar, setSidebar] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const title = location.pathname === '/' || location.pathname === '/dashboard' ? 'Good morning, Avery' : pretty(location.pathname.slice(1).split('/')[0])
  return <div className={`app-shell ${sidebar ? '' : 'sidebar-collapsed'}`}><aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}><div className="sidebar-top"><div className="brand"><span className="brand-icon"><Hotel size={18} /></span><span className="brand-text">AURORA <b>GRAND</b></span></div><button className="icon-button sidebar-close" onClick={() => setMobileOpen(false)}><X size={18} /></button></div><div className="property-switch"><span className="property-dot" /><div><strong>Aurora Grand Hotel</strong><small>Operations workspace</small></div><ChevronRight size={14} /></div><nav><NavSection label="WORKSPACE" items={primaryNav} onNavigate={() => setMobileOpen(false)} /><NavSection label="OPERATIONS" items={operationsNav} onNavigate={() => setMobileOpen(false)} /><NavSection label="FINANCE" items={financeNav} onNavigate={() => setMobileOpen(false)} /></nav><div className="sidebar-bottom"><NavLink to="/settings" className="nav-item" onClick={() => setMobileOpen(false)}><Settings size={17} /><span>Settings</span></NavLink><div className="user-mini"><div className="avatar">{user.first_name[0]}{user.last_name[0]}</div><div className="user-mini-copy"><strong>{user.full_name}</strong><small>{user.roles[0]?.name ?? 'Staff'}</small></div>{testMode ? <span className="test-mode-chip" title="Login is disabled while the platform is being tested">TEST MODE</span> : <button className="icon-button" onClick={onLogout} title="Sign out"><LogOut size={16} /></button>}</div></div></aside><div className="main-area"><header className="topbar"><div className="topbar-left"><button className="icon-button menu-toggle" onClick={() => setMobileOpen(true)}><Menu size={20} /></button><button className="icon-button collapse-toggle" onClick={() => setSidebar((v) => !v)}><PanelLeftClose size={19} /></button><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div></div><div className="topbar-actions"><div className="topbar-date"><CalendarDays size={15} /><span>Monday, Sep 28, 2026</span></div><button className="icon-button notification-button"><Bell size={18} /><i /></button><div className="avatar avatar-top">{user.first_name[0]}{user.last_name[0]}</div></div></header><main className="content"><Routes><Route path="/" element={<DashboardPage />} /><Route path="/dashboard" element={<DashboardPage />} /><Route path="/reservations" element={<ReservationsPage />} /><Route path="/guests" element={<GuestsPage />} /><Route path="/rooms" element={<RoomsPage />} /><Route path="/housekeeping" element={<HousekeepingPage />} /><Route path="/maintenance" element={<MaintenancePage />} /><Route path="/services" element={<ServicesPage />} /><Route path="/finance" element={<FinancePage />} /><Route path="/reports" element={<ReportsPage />} /><Route path="/settings" element={<SettingsPage />} /><Route path="*" element={<DashboardPage />} /></Routes></main></div><ToastHost /></div>
}

function NavSection({ label, items, onNavigate }: { label: string; items: NavItem[]; onNavigate: () => void }) { return <div className="nav-section"><span className="nav-label">{label}</span>{items.map(({ label: itemLabel, icon: Icon, to }) => <NavLink key={to} to={to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={onNavigate}><Icon size={17} /><span>{itemLabel}</span></NavLink>)}</div> }

function PageHeader({ eyebrow, title, subtitle, action, actionLabel, onAction }: { eyebrow?: string; title: string; subtitle?: string; action?: boolean; actionLabel?: string; onAction?: () => void }) { return <div className="page-header"><div><span className="eyebrow">{eyebrow ?? 'AURORA GRAND'}</span><h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}</div>{action && <button className="primary-button" onClick={onAction}><Plus size={17} />{actionLabel}</button>}</div> }

function StatCard({ label, value, detail, icon: Icon, tone, trend }: { label: string; value: string; detail: string; icon: React.ElementType; tone: string; trend?: 'up' | 'down' }) { return <div className="stat-card"><div className="stat-card-top"><span className={`stat-icon ${tone}`}><Icon size={18} /></span>{trend && <span className={`trend ${trend}`} >{trend === 'up' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />} 8.4%</span>}</div><div className="stat-value">{value}</div><div className="stat-label">{label}</div><div className="stat-detail">{detail}</div></div> }

function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null); const [error, setError] = useState('')
  useEffect(() => { api<Dashboard>('/dashboard').then(setData).catch((e) => setError(e.message)) }, [])
  if (error) return <ErrorState message={error} />
  if (!data) return <PageSkeleton />
  const s = data.stats
  return <><PageHeader eyebrow="MONDAY · SEPTEMBER 28, 2026" title="Good morning, Avery" subtitle="Here’s the operational picture for Aurora Grand today." action actionLabel="New reservation" onAction={() => window.location.assign('/reservations')} /><div className="stat-grid"><StatCard label="Occupancy rate" value={`${s.occupancy_rate}%`} detail={`${s.occupied_rooms} of ${s.total_rooms} rooms occupied`} icon={Hotel} tone="teal" trend="up" /><StatCard label="Today's revenue" value={`$${money(s.today_revenue)}`} detail={`$${money(s.month_revenue)} this month`} icon={CircleDollarSign} tone="gold" trend="up" /><StatCard label="Arrivals today" value={String(s.today_check_ins).padStart(2, '0')} detail={`${s.today_check_outs} departures scheduled`} icon={CalendarDays} tone="blue" /><StatCard label="Housekeeping queue" value={String(s.pending_housekeeping).padStart(2, '0')} detail="Tasks need attention" icon={Sparkles} tone="coral" /></div><div className="dashboard-grid"><section className="panel revenue-panel"><PanelTitle title="Revenue overview" meta="Last 14 days" action="View report" href="/reports" /><div className="chart-wrap"><ResponsiveContainer width="100%" height={235}><AreaChart data={data.revenue_trend}><defs><linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2c8c7b" stopOpacity={0.24} /><stop offset="100%" stopColor="#2c8c7b" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e8edf1" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} interval={2} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} tickFormatter={(v) => `$${v}`} width={46} /><Tooltip contentStyle={{ border: '1px solid #d9e2ec', borderRadius: 8, boxShadow: '0 8px 24px rgba(16,42,67,.1)' }} formatter={(value) => [`$${money(String(value))}`, 'Revenue']} /><Area type="monotone" dataKey="value" stroke="#2c8c7b" strokeWidth={2.5} fill="url(#revFill)" /></AreaChart></ResponsiveContainer></div></section><section className="panel rooms-panel"><PanelTitle title="Room utilization" meta="Live status" action="View rooms" href="/rooms" /><div className="utilization"><div className="donut"><ResponsiveContainer width="100%" height={170}><PieChart><Pie data={[{ name: 'Occupied', value: s.occupied_rooms }, { name: 'Available', value: s.available_rooms }, { name: 'Reserved', value: s.reserved_rooms }, { name: 'Other', value: s.cleaning_rooms + s.maintenance_rooms }]} innerRadius={57} outerRadius={73} paddingAngle={3} dataKey="value" stroke="none"><Cell fill="#2c8c7b" /><Cell fill="#dce8e7" /><Cell fill="#e5b567" /><Cell fill="#e8c4bb" /></Pie></PieChart></ResponsiveContainer><div className="donut-center"><strong>{s.total_rooms}</strong><span>rooms</span></div></div><div className="legend"><LegendLine color="#2c8c7b" label="Occupied" value={s.occupied_rooms} /><LegendLine color="#dce8e7" label="Available" value={s.available_rooms} /><LegendLine color="#e5b567" label="Reserved" value={s.reserved_rooms} /><LegendLine color="#e8c4bb" label="Cleaning / OOS" value={s.cleaning_rooms + s.maintenance_rooms} /></div></div></section><section className="panel arrivals-panel"><PanelTitle title="Today at a glance" meta="Front desk" action="Open reservations" href="/reservations" /><div className="arrival-list"><ArrivalMetric icon={ArrowDownRight} label="Arrivals" value={s.today_check_ins} tone="teal" /><ArrivalMetric icon={ArrowUpRight} label="Departures" value={s.today_check_outs} tone="blue" /><ArrivalMetric icon={Users} label="In-house guests" value={s.current_guests} tone="gold" /><ArrivalMetric icon={Receipt} label="Outstanding" value={`$${money(s.outstanding_payments)}`} tone="coral" /></div></section><section className="panel activity-panel"><PanelTitle title="Upcoming arrivals" meta="Next 7 days" action="See calendar" href="/reservations" />{data.upcoming_arrivals.length === 0 ? <EmptyState icon={CalendarDays} title="No upcoming arrivals" copy="The calendar is clear for the next seven days." /> : <div className="mini-table">{data.upcoming_arrivals.slice(0, 4).map((r) => <div className="mini-row" key={r.id}><div className="date-block"><strong>{new Date(r.check_in_date).toLocaleDateString('en-US', { day: '2-digit' })}</strong><span>{new Date(r.check_in_date).toLocaleDateString('en-US', { month: 'short' })}</span></div><div className="mini-main"><strong>{r.guest.full_name}</strong><span>{r.room_type.name} · {r.nights} nights</span></div><span className={`status-pill ${r.status}`}>{pretty(r.status)}</span></div>)}</div>}</section></div></>
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
  const grouped = ['pending', 'in_progress', 'completed']; return <><PageHeader eyebrow="ROOMS DIVISION" title="Housekeeping" subtitle="Keep room readiness visible from the floor to the front desk." action actionLabel="Assign task" /><div className="ops-strip"><span><i className="room-dot dirty" />{data?.items.filter((t) => t.status === 'pending').length ?? 0} pending</span><span><i className="room-dot cleaning" />{data?.items.filter((t) => t.status === 'in_progress').length ?? 0} in progress</span><span><i className="room-dot available" />{data?.items.filter((t) => t.status === 'completed').length ?? 0} completed today</span><span className="ops-spacer" /><span className="muted">Today · Sep 28, 2026</span></div><div className="kanban">{grouped.map((status) => <section className="kanban-column" key={status}><div className="kanban-head"><span>{pretty(status)}</span><b>{data?.items.filter((t) => t.status === status).length ?? 0}</b></div>{data?.items.filter((t) => t.status === status).map((task) => <div className="task-card" key={task.id}><div className="task-card-head"><strong>Room {task.room?.number ?? '—'}</strong><span className={`priority ${task.priority}`}>{pretty(task.priority)}</span></div><span className="task-type">{pretty(task.task_type)}</span><div className="task-card-foot"><span className="avatar avatar-tiny">SP</span><span>Sofia Patel</span><RowMenu size={16} actions={[...(task.status === 'pending' ? [{ label: 'Start cleaning', icon: Play, disabled: busyId === task.id, onClick: () => patch(task, { status: 'in_progress' }, `Room ${task.room?.number ?? ''} cleaning started`) }] : []), ...(task.status !== 'completed' ? [{ label: 'Mark completed', icon: Check, disabled: busyId === task.id, onClick: () => patch(task, { status: 'completed' }, `Room ${task.room?.number ?? ''} marked clean`) }] : []), { label: 'Set high priority', icon: AlertTriangle, disabled: busyId === task.id || task.priority === 'high', onClick: () => patch(task, { priority: 'high' }, 'Priority raised to high') }]} /></div></div>)}{data?.items.filter((t) => t.status === status).length === 0 && <div className="column-empty"><Check size={18} /><span>All clear</span></div>}</section>)}</div></> }

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

function FinancePage() { const [data, setData] = useState<Page<Payment> | null>(null); useEffect(() => { api<Page<Payment>>('/payments?page_size=30').then(setData).catch(() => undefined) }, []); return <><PageHeader eyebrow="FINANCE" title="Payments" subtitle="A clean, auditable view of every money movement." action actionLabel="Record payment" /><div className="finance-summary"><div><span>Total collected this month</span><strong>$24,820.00</strong><small className="success-text"><ArrowUpRight size={14} /> 12.8% vs. last month</small></div><div><span>Outstanding balances</span><strong>$5,014.24</strong><small>Across active stays</small></div><div><span>Payment success rate</span><strong>99.2%</strong><small>Last 30 days</small></div></div><section className="panel table-panel"><PanelTitle title="Recent payments" meta="Live ledger" action="Export CSV" /><div className="table-scroll"><table><thead><tr><th>Payment</th><th>Reservation</th><th>Method</th><th>Date</th><th>Amount</th><th>Status</th><th /></tr></thead><tbody>{data?.items.map((p) => <tr key={p.id}><td><strong className="mono">{p.number}</strong><small>{p.entry_type === 'refund' ? 'Refund' : 'Charge'}</small></td><td><strong>Reservation folio</strong><small className="mono">{p.id.slice(0, 8).toUpperCase()}</small></td><td><span className="method"><span className="method-dot" />{p.method_label}</span></td><td>{formatDate(p.paid_at)}</td><td><strong className={p.entry_type === 'refund' ? 'warning-text' : ''}>{p.entry_type === 'refund' ? '−' : ''}${money(p.amount)}</strong></td><td><span className="status-pill paid">{pretty(p.status)}</span></td><td><button className="icon-button"><MoreHorizontal size={17} /></button></td></tr>)}</tbody></table>{data?.items.length === 0 && <EmptyState icon={CircleDollarSign} title="No payments yet" copy="Payments will appear here when a guest settles their folio." />}</div></section></> }

function ReportsPage() { const [report, setReport] = useState<{ summary: { total_revenue?: string; payment_count?: number }; series: { label: string; value: string }[] } | null>(null); useEffect(() => { api<typeof report>('/reports/revenue').then(setReport).catch(() => undefined) }, []); return <><PageHeader eyebrow="INSIGHTS" title="Reports" subtitle="The signals behind confident operating decisions." /><div className="report-tabs"><button className="active">Revenue</button><button>Occupancy</button><button>Reservations</button><button>Expenses</button><button>Housekeeping</button></div><section className="report-hero panel"><div><span className="eyebrow">REVENUE PERFORMANCE</span><h2>${money(report?.summary.total_revenue)}</h2><p className="muted">Total recorded revenue · last 30 days</p></div><div className="report-actions"><button className="secondary-button"><CalendarDays size={15} />Last 30 days</button><button className="secondary-button"><FileText size={15} />Export</button></div></section><section className="panel report-chart"><PanelTitle title="Daily revenue" meta="USD · All payment methods" />{report && <ResponsiveContainer width="100%" height={300}><BarChart data={report.series}><CartesianGrid vertical={false} stroke="#e8edf1" /><XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} interval={3} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#82909d', fontSize: 11 }} /><Tooltip formatter={(v) => [`$${money(String(v))}`, 'Revenue']} /><Bar dataKey="value" fill="#2c8c7b" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer>}</section></> }

function SettingsPage() { return <><PageHeader eyebrow="ADMINISTRATION" title="Settings" subtitle="Configuration for the Aurora Grand workspace." /><div className="settings-grid"><section className="panel settings-card"><div className="settings-card-icon"><Hotel size={19} /></div><h3>Hotel profile</h3><p>Property details, contact information and branding.</p><button className="text-button">Manage profile <ChevronRight size={15} /></button></section><section className="panel settings-card"><div className="settings-card-icon"><ShieldCheck size={19} /></div><h3>Access & roles</h3><p>Manage staff accounts, roles and permissions.</p><button className="text-button">Manage access <ChevronRight size={15} /></button></section><section className="panel settings-card"><div className="settings-card-icon"><Receipt size={19} /></div><h3>Billing configuration</h3><p>Taxes, invoice numbering and accepted payment methods.</p><button className="text-button">Configure billing <ChevronRight size={15} /></button></section><section className="panel settings-card"><div className="settings-card-icon"><Activity size={19} /></div><h3>Audit trail</h3><p>Immutable record of important system activity.</p><button className="text-button">View audit log <ChevronRight size={15} /></button></section></div></> }

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
