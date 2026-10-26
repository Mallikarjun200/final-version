const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export function apiFetch(path, options = {}) {
  const workspaceId = window.localStorage.getItem('stackly-workspace-id')
  return fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...(workspaceId ? { 'X-Workspace-ID': workspaceId } : {}),
      ...options.headers,
    },
  })
}
