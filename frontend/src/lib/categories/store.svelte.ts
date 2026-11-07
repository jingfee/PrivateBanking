import { api, type Category } from '$lib/api';

export type CategoryKind = 'expense' | 'income' | 'transfer' | 'reimbursement';

/** A category with color and kind resolved from its parent. */
export type ResolvedCategory = Category & {
  color: string;
  parent: Category | null;
  /** "Mat & dryck › Livsmedel", or just the name for a top-level category */
  path: string;
};

export type CategoryGroup = { group: ResolvedCategory; children: ResolvedCategory[] };

let all = $state<Category[]>([]);
let loading: Promise<void> | null = null;

const resolved = $derived.by(() => {
  const byId = new Map(all.map((c) => [c.id, c]));
  const out = new Map<number, ResolvedCategory>();
  for (const c of all) {
    const parent = c.parent_id ? (byId.get(c.parent_id) ?? null) : null;
    out.set(c.id, {
      ...c,
      parent,
      color: c.color ?? parent?.color ?? 'gray',
      path: parent ? `${parent.name} › ${c.name}` : c.name
    });
  }
  return out;
});

const groups = $derived.by(() => {
  const list: CategoryGroup[] = [];
  for (const c of resolved.values()) if (c.parent_id === null) list.push({ group: c, children: [] });
  const byId = new Map(list.map((g) => [g.group.id, g]));
  for (const c of resolved.values()) if (c.parent_id !== null) byId.get(c.parent_id)?.children.push(c);
  list.sort((a, b) => a.group.sort_order - b.group.sort_order);
  for (const g of list) g.children.sort((a, b) => a.sort_order - b.sort_order);
  return list;
});

export const categories = {
  get groups() {
    return groups;
  },
  get(id: number | null | undefined): ResolvedCategory | undefined {
    return id == null ? undefined : resolved.get(id);
  },
  /** Load once; later calls reuse the same request. */
  load(force = false): Promise<void> {
    if (!loading || force) {
      loading = api.categories().then((c) => {
        all = c;
      });
      loading.catch(() => (loading = null));
    }
    return loading;
  }
};
