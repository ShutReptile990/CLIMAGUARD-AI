const API_SUFFIX = '/api/v1'

export function normalizeApiBase(rawValue: string | undefined, production: boolean): string {
  const value = rawValue?.trim()
  if (!value) {
    if (production) {
      throw new Error('VITE_API_BASE_URL is required for production builds. Set it to the HTTPS origin of the Render backend.')
    }
    return ''
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute http(s) URL.')
  }

  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('VITE_API_BASE_URL must be a plain http(s) origin without credentials, query parameters, or fragments.')
  }
  if (production && url.protocol !== 'https:') {
    throw new Error('VITE_API_BASE_URL must use HTTPS in production.')
  }

  const path = url.pathname.replace(/\/+$/, '')
  if (path && path !== '/api' && path !== API_SUFFIX) {
    throw new Error('VITE_API_BASE_URL must contain only the backend origin (an optional /api or /api/v1 suffix is accepted).')
  }
  return url.origin
}

export function buildApiUrl(base: string, path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${base}${API_SUFFIX}${normalizedPath}`
}
