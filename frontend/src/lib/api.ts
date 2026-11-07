export type Transaction = {
  id: number;
  date: string | null;
  status: 'BOOK' | 'PDNG';
  description: string;
  amount_ore: number;
  currency: string;
  account_id: number;
  account: string;
  aspsp: string;
  mcc: string | null;
  category_id: number | null;
  category_source: 'manual' | 'learned' | 'auto' | null;
};

export type Category = {
  id: number;
  parent_id: number | null;
  key: string | null;
  name: string;
  kind: 'expense' | 'income' | 'transfer' | 'reimbursement';
  color: string | null;
  icon: string | null;
  sort_order: number;
  transaction_count: number;
};

export type CategoryInput = {
  name?: string;
  parent_id?: number | null;
  kind?: Category['kind'];
  color?: string;
  icon?: string;
};

export type Account = {
  id: number;
  aspsp: string;
  name: string | null;
  identifier: string | null;
  currency: string | null;
  active: boolean;
  last_synced_at: string | null;
  transaction_count: number;
  connection_status: string | null;
  valid_until: string | null;
  last_error: string | null;
};

export type Bank = { name: string; country: string; logo: string | null };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  transactions: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') qs.set(k, String(v));
    return request<{ total: number; items: Transaction[] }>(`/api/transactions?${qs}`);
  },
  setCategory: (id: number, category_id: number | null) =>
    request<Transaction & { similar_updated: number }>(`/api/transactions/${id}`, { method: 'PATCH', body: JSON.stringify({ category_id }) }),
  categories: () => request<Category[]>('/api/categories'),
  createCategory: (body: CategoryInput) =>
    request<Category>('/api/categories', { method: 'POST', body: JSON.stringify(body) }),
  updateCategory: (id: number, body: CategoryInput) =>
    request<Category>(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteCategory: (id: number) =>
    request<{ deleted: number; transactions: number }>(`/api/categories/${id}`, { method: 'DELETE' }),
  accounts: () => request<Account[]>('/api/accounts'),
  banks: () => request<Bank[]>('/api/aspsps'),
  connect: (aspsp: string) =>
    request<{ url: string }>('/api/connections', { method: 'POST', body: JSON.stringify({ aspsp }) }),
  sync: () => request<unknown[]>('/api/sync', { method: 'POST' })
};

const kr = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatAmount(ore: number): string {
  const s = kr.format(Math.abs(ore) / 100);
  return ore < 0 ? `−${s}` : `+${s}`;
}

const dayFmt = new Intl.DateTimeFormat('sv-SE', { weekday: 'long', day: 'numeric', month: 'long' });
const dayYearFmt = new Intl.DateTimeFormat('sv-SE', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric'
});

export function formatDay(iso: string | null): string {
  if (!iso) return 'Utan datum';
  const d = new Date(`${iso}T12:00:00`);
  const today = new Date();
  const diff = Math.round((today.setHours(12, 0, 0, 0) - d.getTime()) / 86400000);
  if (diff === 0) return 'I dag';
  if (diff === 1) return 'I går';
  return (d.getFullYear() === new Date().getFullYear() ? dayFmt : dayYearFmt).format(d);
}

export function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('sv-SE') : '–';
}
