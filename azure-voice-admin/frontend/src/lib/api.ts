/**
 * Authenticated fetch wrapper. Includes credentials and handles 401 → redirect to login.
 */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, {
    ...init,
    credentials: 'include',
  })
  if (res.status === 401 && typeof window !== 'undefined') {
    // Session expired or not authenticated
    window.location.href = '/login'
  }
  return res
}
