export type ApiError = { error?: { code?: string; message?: string; details?: unknown } }

const API = '/api/v1'

function csrfToken() {
  return document.cookie.split('; ').find((part) => part.startsWith('hms_csrf='))?.split('=')[1]
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = csrfToken()
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const res = await fetch(`${API}${path}`, { ...options, headers, credentials: 'include' })
  if (res.status === 401 && path !== '/auth/login') {
    // The next request (or the auth provider) will handle re-authentication.
    window.dispatchEvent(new CustomEvent('hms:unauthorized'))
  }
  if (!res.ok) {
    let payload: ApiError = {}
    try { payload = await res.json() } catch { /* non-json error */ }
    throw new Error(payload.error?.message ?? `Request failed (${res.status})`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
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
