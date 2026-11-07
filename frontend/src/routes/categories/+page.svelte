<script lang="ts">
  import { api, type Category, type CategoryInput } from '$lib/api';
  import CategoryEditor, { KINDS } from '$lib/categories/CategoryEditor.svelte';
  import CategoryIcon from '$lib/categories/CategoryIcon.svelte';
  import { categories, type CategoryGroup } from '$lib/categories/store.svelte';

  type Editing = { category: Category | null; parent: Category | null; affected: number };

  let editing = $state<Editing | null>(null);
  let error = $state('');
  let message = $state('');

  const kindLabel = (k: string) => KINDS.find((x) => x.value === k)?.label ?? k;
  const total = (g: CategoryGroup) => g.children.reduce((s, c) => s + c.transaction_count, g.group.transaction_count);

  async function reload() {
    try {
      await categories.load(true);
    } catch (e) {
      error = `Kunde inte hämta kategorier: ${(e as Error).message}`;
    }
  }

  async function save(input: CategoryInput) {
    const e = editing!;
    if (e.category) await api.updateCategory(e.category.id, input);
    else await api.createCategory({ ...input, parent_id: e.parent?.id ?? null });
    message = '';
    await reload();
  }

  async function remove() {
    const c = editing!.category!;
    const r = await api.deleteCategory(c.id);
    message = r.transactions
      ? `${c.name} är borttagen. ${r.transactions} transaktioner kategoriserades om.`
      : `${c.name} är borttagen.`;
    await reload();
  }

  $effect(() => {
    reload();
  });
</script>

<p class="intro muted">
  Typen styr hur beloppen räknas: utgifter och inkomster som vanligt, ersättningar minskar dina utgifter och
  överföringar räknas inte alls.
</p>

{#if message}<p class="notice" role="status">{message}</p>{/if}
{#if error}<p class="error">{error}</p>{/if}

{#each categories.groups as g (g.group.id)}
  {@const group = g.group}
  <section>
    <header>
      <button
        type="button"
        class="row head"
        onclick={() => (editing = { category: group, parent: null, affected: total(g) })}
      >
        <CategoryIcon icon={group.icon} color={group.color} size={36} />
        <span class="name">
          <strong>{group.name}</strong>
          <span class="muted small">{kindLabel(group.kind)} · {total(g)} transaktioner</span>
        </span>
        <span class="edit muted small">Ändra</span>
      </button>
    </header>
    <ul>
      {#each g.children as c (c.id)}
        <li>
          <button
            type="button"
            class="row"
            onclick={() => (editing = { category: c, parent: group, affected: c.transaction_count })}
          >
            <CategoryIcon icon={c.icon} color={c.color} size={30} />
            <span class="name">{c.name}</span>
            <span class="muted small num">{c.transaction_count || ''}</span>
          </button>
        </li>
      {/each}
      <li>
        <button type="button" class="row add" onclick={() => (editing = { category: null, parent: group, affected: 0 })}>
          <span class="plus" aria-hidden="true">+</span>
          <span class="name">Lägg till underkategori</span>
        </button>
      </li>
    </ul>
  </section>
{/each}

<button type="button" class="new" onclick={() => (editing = { category: null, parent: null, affected: 0 })}>
  + Ny huvudkategori
</button>

{#if editing}
  <CategoryEditor
    category={editing.category}
    parent={editing.parent}
    affected={editing.affected}
    onsave={save}
    ondelete={editing.category ? remove : undefined}
    onclose={() => (editing = null)}
  />
{/if}

<style>
  .intro { font-size: 0.88rem; margin: 0 0 8px; }
  .notice {
    padding: 8px 12px; font-size: 0.9rem;
    background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
  }
  section {
    margin-top: 16px; background: var(--surface);
    border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden;
  }
  ul { list-style: none; margin: 0; padding: 0; }
  li { border-top: 1px solid var(--rule); }
  .row {
    display: flex; align-items: center; gap: 12px; width: 100%; text-align: left;
    border: none; border-radius: 0; background: none; padding: 8px 14px;
  }
  .row:hover { background: color-mix(in srgb, var(--ink) 4%, transparent); }
  .row.head { padding: 12px 14px; }
  li .row { padding-left: 28px; }
  .name { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .name, .name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .small { font-size: 0.8rem; }
  .add { color: var(--accent); }
  .plus {
    display: inline-grid; place-items: center; width: 30px; height: 30px; flex: none;
    border-radius: 50%; border: 1.5px dashed currentColor; font-weight: 600;
  }
  .new { display: block; margin: 20px auto 0; }
</style>
