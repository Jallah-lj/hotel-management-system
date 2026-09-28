export type ApiError = { error?: { code?: string; message?: string; details?: unknown } }

const API = '/api/v1'
const SESSION_TOKEN_KEY = 'hms_access_token'

// The first-party production app uses HttpOnly cookies. The preview proxy can
// be embedded under a different top-level origin, where browser cookie
// partitioning varies by browser. Keep a short-lived bearer fallback only for
// local/Arena preview hosts; production domains remain cookie-only.
function previewStorageEnabled() {
  return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.hostname.endsWith('.e2b.app')
}

function getAccessToken() {
  try {
    return sessionStorage.getItem(SESSION_TOKEN_KEY) || (previewStorageEnabled() ? localStorage.getItem(SESSION_TOKEN_KEY) : null)
  } catch { return null }
}

function setAccessToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(SESSION_TOKEN_KEY, token)
    else sessionStorage.removeItem(SESSION_TOKEN_KEY)
    if (previewStorageEnabled()) {
      if (token) localStorage.setItem(SESSION_TOKEN_KEY, token)
      else localStorage.removeItem(SESSION_TOKEN_KEY)
    }
  } catch { /* storage may be unavailable in hardened browsers */ }
}

export function clearSession() { setAccessToken(null) }

function csrfToken() {
  return document.cookie.split('; ').find((part) => part.startsWith('hms_csrf='))?.split('=')[1]
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const accessToken = getAccessToken()
  if (accessToken && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${accessToken}`)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = csrfToken()
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const res = await fetch(`${API}${path}`, { ...options, headers, credentials: 'include' })
  if (res.status === 401 && path !== '/auth/login' && path !== '/auth/refresh') {
    // Access tokens are intentionally short-lived. Rotate the HttpOnly refresh
    // session once before sending the user back to the login screen.
    const refreshed = await fetch(`${API}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include' })
    if (refreshed.ok) {
      const session = await refreshed.json() as { access_token?: string }
      setAccessToken(session.access_token ?? null)
      return api<T>(path, options)
    }
    clearSession()
    window.dispatchEvent(new CustomEvent('hms:unauthorized'))
  }
  if (!res.ok) {
    let payload: ApiError = {}
    try { payload = await res.json() } catch { /* non-json error */ }
    throw new Error(payload.error?.message ?? `Request failed (${res.status})`)
  }
  if (res.status === 204) return undefined as T
  const payload = await res.json() as T & { access_token?: string }
  if (path === '/auth/login' || path === '/auth/refresh') setAccessToken(payload.access_token ?? null)
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
