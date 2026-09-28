export type ApiError = { error?: { code?: string; message?: string; details?: unknown } }

export class ApiRequestError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

export class ApiNetworkError extends Error {
  constructor() {
    super('Unable to connect to the hotel server.')
    this.name = 'ApiNetworkError'
  }
}

const API = '/api/v1'
const SESSION_TOKEN_KEY = 'hms_access_token'

// Keep an in-memory copy as a final fallback for embedded previews where
// browser storage is disabled by iframe/privacy policy. A successful login
// must remain usable for the current page even when cookies and storage are
// unavailable.

// The first-party production app uses HttpOnly cookies. The preview proxy can
// be embedded under a different top-level origin, where browser cookie
// partitioning varies by browser. Keep a short-lived bearer fallback only for
// local/Arena preview hosts; production domains remain cookie-only.
export function isPreviewHost() {
  // Local and Arena hosts are isolated preview environments. The hostname
  // check is intentional so a production-style bundle served by the Arena
  // preview still gets its preview-safe session fallback.
  return import.meta.env.DEV || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.hostname.includes('e2b.app')
}

function previewStorageEnabled() {
  return isPreviewHost()
}

let memoryAccessToken: string | null = null

function getAccessToken() {
  try {
    return sessionStorage.getItem(SESSION_TOKEN_KEY) || (previewStorageEnabled() ? localStorage.getItem(SESSION_TOKEN_KEY) : null) || memoryAccessToken
  } catch { return memoryAccessToken }
}

function setAccessToken(token: string | null) {
  memoryAccessToken = token
  try {
    if (token) sessionStorage.setItem(SESSION_TOKEN_KEY, token)
    else sessionStorage.removeItem(SESSION_TOKEN_KEY)
    if (previewStorageEnabled()) {
      if (token) localStorage.setItem(SESSION_TOKEN_KEY, token)
      else localStorage.removeItem(SESSION_TOKEN_KEY)
    }
  } catch { /* storage may be unavailable in hardened browsers */ }
}

export function rememberUser(user: User) {
  try {
    sessionStorage.setItem('hms_user', JSON.stringify(user))
    if (previewStorageEnabled()) localStorage.setItem('hms_user', JSON.stringify(user))
  } catch { /* storage may be unavailable in hardened browsers */ }
}

export function rememberedUser(): User | null {
  try {
    const raw = sessionStorage.getItem('hms_user') || (previewStorageEnabled() ? localStorage.getItem('hms_user') : null)
    return raw ? JSON.parse(raw) as User : null
  } catch { return null }
}

export function clearSession() {
  setAccessToken(null)
  try {
    sessionStorage.removeItem('hms_user')
    if (previewStorageEnabled()) localStorage.removeItem('hms_user')
  } catch { /* storage may be unavailable in hardened browsers */ }
}

function csrfToken() {
  return document.cookie.split('; ').find((part) => part.startsWith('hms_csrf='))?.split('=')[1]
}

const AUTH_PATHS = new Set(['/auth/login', '/auth/refresh', '/auth/demo-login'])

function authDebug(message: string, details?: Record<string, unknown>) {
  if (isPreviewHost()) console.info(`[AUTH] ${message}`, details ?? '')
}

export async function api<T>(path: string, options: RequestInit = {}, allowRefresh = true): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const accessToken = getAccessToken()
  if (accessToken && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${accessToken}`)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = csrfToken()
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }

  authDebug('request', { method, path, hasBearer: Boolean(accessToken), allowRefresh })
  let res: Response
  try {
    res = await fetch(`${API}${path}`, { ...options, headers, credentials: 'include' })
  } catch {
    authDebug('network failure', { method, path })
    throw new ApiNetworkError()
  }
  authDebug('response', { method, path, status: res.status })

  if (res.status === 401 && !AUTH_PATHS.has(path)) {
    if (allowRefresh) {
      // Access tokens are intentionally short-lived. Rotate the refresh session
      // at most once; a bounded retry prevents an invalid refresh configuration
      // from creating an infinite request/redirect loop.
      try {
        const refreshed = await fetch(`${API}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include' })
        authDebug('refresh response', { status: refreshed.status })
        if (refreshed.ok) {
          const session = await refreshed.json() as { access_token?: string }
          setAccessToken(session.access_token ?? null)
          authDebug('refresh credential stored', { hasAccessToken: Boolean(session.access_token) })
          return api<T>(path, options, false)
        }
      } catch {
        // The original request remains an authentication failure below.
      }
    }
    authDebug('session rejected; clearing client session', { path })
    clearSession()
    window.dispatchEvent(new CustomEvent('hms:unauthorized'))
  }

  if (!res.ok) {
    let payload: ApiError = {}
    try { payload = await res.json() } catch { /* non-json error */ }
    const code = payload.error?.code ?? (res.status === 401 ? 'not_authenticated' : res.status === 403 ? 'permission_denied' : 'request_failed')
    throw new ApiRequestError(res.status, code, payload.error?.message ?? `Request failed (${res.status})`)
  }
  if (res.status === 204) return undefined as T
  const payload = await res.json() as T & { access_token?: string }
  if (AUTH_PATHS.has(path)) {
    setAccessToken(payload.access_token ?? null)
    authDebug('credential stored', { path, hasAccessToken: Boolean(payload.access_token) })
  }
  return payload as T
}

export type Page<T> = { items: T[]; total: number; page: number; page_size: number; pages: number; has_next: boolean; has_previous: boolean }
export type User = { id: string; email: string; username: string; full_name: string; first_name: string; last_name: string; job_title?: string; department?: string; status: string; is_superuser: boolean; must_change_password: boolean; roles: { code: string; name: string; level: number }[]; permissions: string[] }
export type Room = { id: string; number: string; name?: string; room_type_id: string; room_type: { id: string; code: string; name: string; base_price: string; max_occupancy: number; bed_type: string }; floor: number; price_per_night: string; status: string; housekeeping_condition: string; maintenance_flag: string; capacity: number; is_bookable: boolean }
export type Guest = { id: string; reference: string; full_name: string; first_name: string; last_name: string; email?: string; phone?: string; nationality?: string; is_vip: boolean; total_stays: number; total_spend: string; outstanding_balance: string; created_at: string }
export type Reservation = { id: string; reference: string; guest: { id: string; reference: string; full_name: string; email?: string; phone?: string; is_vip: boolean }; room_type: { name: string }; room?: { number: string }; check_in_date: string; check_out_date: string; nights: number; adults: number; children: number; total_amount: string; paid_amount: string; balance: string; status: string; payment_status: string; booking_source: string }
export type Dashboard = { stats: { total_rooms: number; available_rooms: number; occupied_rooms: number; reserved_rooms: number; cleaning_rooms: number; maintenance_rooms: number; occupancy_rate: number; today_check_ins: number; today_check_outs: number; current_guests: number; today_revenue: string; month_revenue: string; outstanding_payments: string; pending_housekeeping: number }; revenue_trend: { label: string; value: string }[]; reservation_mix: { label: string; value: number }[]; payment_methods: { label: string; value: string }[]; upcoming_arrivals: Reservation[]; upcoming_departures: Reservation[] }
export type Task = { id: string; room_id: string; task_type: string; status: string; priority: string; scheduled_date: string; assigned_to_id?: string; room?: Room }
export type Ticket = { id: string; ticket_number: string; title: string; category: string; priority: string; status: string; description: string; reported_at: string; room_id?: string }
export type Payment = { id: string; number: string; amount: string; currency: string; method_label: string; status: string; paid_at: string; entry_type: string }
export type Service = { id: string; code: string; name: string; category: string; price: string; tax_rate: string; unit: string; is_active: boolean }
