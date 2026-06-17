const API_BASE = '/api';

function getToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${url}`, { ...options, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }
  return response.json();
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      request<{ access_token: string; token_type: string }>('/auth/login', {
        method: 'POST', body: JSON.stringify({ email, password }),
      }),
    register: (email: string, password: string, name?: string) =>
      request<{ access_token: string; token_type: string }>('/auth/register', {
        method: 'POST', body: JSON.stringify({ email, password, name }),
      }),
    me: () => request<{ id: number; email: string; name: string | null; is_admin: boolean }>('/auth/me'),
  },
  tools: {
    list: (params?: { category?: string; search?: string; page?: number }) => {
      const q = new URLSearchParams();
      if (params?.category) q.set('category', params.category);
      if (params?.search) q.set('search', params.search);
      if (params?.page) q.set('page', String(params.page));
      return request<{ tools: any[]; total: number }>(`/tools?${q}`);
    },
    get: (slug: string) => request<any>(`/tools/${slug}`),
    search: (q: string) => request<any[]>(`/search?q=${encodeURIComponent(q)}`),
  },
  categories: {
    list: () => request<any[]>('/categories'),
  },
  submissions: {
    create: (data: { name: string; url: string; category_slug?: string; description?: string; submitter_email?: string }) =>
      request<{ id: number; status: string; message: string }>('/submissions', {
        method: 'POST', body: JSON.stringify(data),
      }),
  },
  reviews: {
    list: (slug: string) => request<any[]>(`/tools/${slug}/reviews`),
    create: (slug: string, rating: number, body?: string) =>
      request<any>(`/tools/${slug}/reviews`, {
        method: 'POST', body: JSON.stringify({ rating, body }),
      }),
  },
  favorites: {
    list: () => request<any[]>('/favorites'),
    add: (toolId: number) => request<any>('/favorites', {
      method: 'POST', body: JSON.stringify({ tool_id: toolId }),
    }),
    remove: (toolId: number) => request<any>(`/favorites/${toolId}`, { method: 'DELETE' }),
    check: (slug: string) => request<{ favorited: boolean }>(`/favorites/check/${slug}`),
    addBySlug: (slug: string) => request<any>(`/favorites/slug/${slug}`, { method: 'POST' }),
    removeBySlug: (slug: string) => request<any>(`/favorites/slug/${slug}`, { method: 'DELETE' }),
  },
  contact: (data: { name: string; email: string; message: string }) =>
    request<any>('/contact', { method: 'POST', body: JSON.stringify(data) }),
  newsletter: (email: string) =>
    request<any>('/newsletter', { method: 'POST', body: JSON.stringify({ email }) }),
  admin: {
    stats: () => request<any>('/admin/stats'),
    submissions: (status?: string) => request<any[]>(`/admin/submissions${status ? `?status_filter=${status}` : ''}`),
    approveSubmission: (id: number) => request<any>(`/admin/submissions/${id}/approve`, { method: 'POST' }),
    rejectSubmission: (id: number) => request<any>(`/admin/submissions/${id}/reject`, { method: 'POST' }),
    messages: () => request<any[]>('/admin/messages'),
    costReports: () => request<any[]>('/admin/cost-reports'),
    costReport: (id: number) => request<any>(`/admin/cost-reports/${id}`),
  },
  analysis: {
    run: (data?: { triggered_by?: string }) =>
      request<{ report_uuid: string; status: string; message: string }>('/analysis/run', {
        method: 'POST', body: JSON.stringify(data || {}),
      }),
    reports: () => request<any[]>('/analysis/reports'),
    report: (id: number) => request<any>(`/analysis/reports/${id}`),
  },
};
