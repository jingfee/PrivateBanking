<script lang="ts">
  import { api, formatAmount, formatDay, type Account, type Transaction } from '$lib/api';
  import CategoryIcon from '$lib/categories/CategoryIcon.svelte';
  import CategoryPicker from '$lib/categories/CategoryPicker.svelte';
  import { categories } from '$lib/categories/store.svelte';

  const PAGE = 100;
  let items = $state<Transaction[]>([]);
  let total = $state(0);
  let accounts = $state<Account[]>([]);
  let q = $state('');
  let account = $state('');
  let from = $state('');
  let to = $state('');
  let category = $state('');
  let picking = $state<Transaction | null>(null);
  let notice = $state('');
  let loading = $state(true);
  let error = $state('');

  const days = $derived.by(() => {
    const groups: { date: string | null; items: Transaction[]; sum: number }[] = [];
    for (const t of items) {
      const last = groups.at(-1);
      if (last && last.date === t.date) {
        last.items.push(t);
        last.sum += t.amount_ore;
      } else groups.push({ date: t.date, items: [t], sum: t.amount_ore });
    }
    return groups;
  });

  async function load(append = false) {
    loading = true;
    error = '';
    try {
      const res = await api.transactions({ q, account, from, to, category, limit: PAGE, offset: append ? items.length : 0 });
      items = append ? [...items, ...res.items] : res.items;
      total = res.total;
    } catch (e) {
      error = `Kunde inte hämta transaktioner: ${(e as Error).message}`;
    } finally {
      loading = false;
    }
  }

  /** Reload what is already shown, e.g. after other rows changed category. */
  async function refresh() {
    const res = await api.transactions({ q, account, from, to, category, limit: Math.max(items.length, PAGE) });
    items = res.items;
    total = res.total;
  }

  let timer: ReturnType<typeof setTimeout>;
  function search() {
    clearTimeout(timer);
    timer = setTimeout(() => load(), 250);
  }

  async function setCategory(t: Transaction, id: number | null) {
    picking = null;
    notice = '';
    try {
      const updated = await api.setCategory(t.id, id);
      items = items.map((i) => (i.id === t.id ? { ...i, ...updated } : i));
      const n = updated.similar_updated;
      if (n > 0) {
        const name = id === null ? null : categories.get(id)?.name;
        notice = name
          ? `${n} ${n === 1 ? 'liknande transaktion' : 'liknande transaktioner'} fick också kategorin ${name}.`
          : `${n} ${n === 1 ? 'liknande transaktion' : 'liknande transaktioner'} kategoriserades om.`;
        await refresh();
      }
    } catch (e) {
      error = `Kunde inte spara kategorin: ${(e as Error).message}`;
    }
  }

  $effect(() => {
    api.accounts().then((a) => (accounts = a)).catch(() => {});
    categories.load().catch((e) => (error = `Kunde inte hämta kategorier: ${(e as Error).message}`));
    load();
  });
</script>

<form class="filters" onsubmit={(e) => { e.preventDefault(); load(); }}>
  <input type="search" placeholder="Sök beskrivning" aria-label="Sök beskrivning" bind:value={q} oninput={search} />
  <select aria-label="Konto" bind:value={account} onchange={() => load()}>
    <option value="">Alla konton</option>
    {#each accounts as a (a.id)}
      <option value={String(a.id)}>{a.name ?? a.aspsp}</option>
    {/each}
  </select>
  <select aria-label="Kategori" bind:value={category} onchange={() => load()}>
    <option value="">Alla kategorier</option>
    <option value="none">Okategoriserade</option>
    {#each categories.groups as { group, children } (group.id)}
      <optgroup label={group.name}>
        <option value={String(group.id)}>Alla i {group.name}</option>
        {#each children as c (c.id)}
          <option value={String(c.id)}>{c.name}</option>
        {/each}
      </optgroup>
    {/each}
  </select>
  <label>Från <input type="date" bind:value={from} onchange={() => load()} /></label>
  <label>Till <input type="date" bind:value={to} onchange={() => load()} /></label>
</form>

{#if notice}
  <p class="notice" role="status">
    <span>{notice}</span>
    <button type="button" aria-label="Stäng" onclick={() => (notice = '')}>✕</button>
  </p>
{/if}

{#if error}
  <p class="error">{error}</p>
{:else if !loading && items.length === 0}
  <div class="empty">
    {#if q || account || from || to || category}
      <p>Inga transaktioner matchar filtret.</p>
    {:else}
      <p>Inga transaktioner än.</p>
      <p><a href="/accounts">Koppla en bank</a> för att hämta dem.</p>
    {/if}
  </div>
{/if}

{#each days as day (day.date)}
  <section>
    <h2>
      <span>{formatDay(day.date)}</span>
      <span class="num daysum" class:in={day.sum > 0}>{formatAmount(day.sum)}</span>
    </h2>
    <ul>
      {#each day.items as t (t.id)}
        {@const cat = categories.get(t.category_id)}
        <li class:pending={t.status === 'PDNG'}>
          <button
            type="button"
            class="cat"
            aria-label={cat ? `Kategori: ${cat.path}. Ändra` : 'Välj kategori'}
            title={cat?.path ?? 'Välj kategori'}
            onclick={() => (picking = t)}
          >
            <CategoryIcon icon={cat?.icon} color={cat?.color} size={36} />
          </button>
          <div class="what">
            <span class="desc">{t.description || 'Okänd transaktion'}</span>
            <span class="meta muted">
              <span class="catname">{cat?.name ?? 'Okategoriserad'}</span>
              <span aria-hidden="true">·</span>
              <span class="acct">{t.account}</span>
              {#if t.status === 'PDNG'}<span class="tag">Reserverad</span>{/if}
            </span>
          </div>
          <span class="amount num" class:in={t.amount_ore > 0}>
            {formatAmount(t.amount_ore)}{#if t.currency !== 'SEK'}&nbsp;{t.currency}{/if}
          </span>
        </li>
      {/each}
    </ul>
  </section>
{/each}

{#if picking}
  {@const t = picking}
  <CategoryPicker
    title={t.description || 'Okänd transaktion'}
    current={t.category_id}
    source={t.category_source}
    onselect={(id) => setCategory(t, id)}
    onclose={() => (picking = null)}
  />
{/if}

{#if items.length < total}
  <button class="more" disabled={loading} onclick={() => load(true)}>
    Visa fler ({total - items.length} kvar)
  </button>
{/if}

<style>
  .filters { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }
  .filters > input, .filters > select { grid-column: 1 / -1; width: 100%; }
  .filters label { display: flex; flex-direction: column; gap: 2px; color: var(--muted); font-size: 0.8rem; min-width: 0; }
  .filters label input { width: 100%; }
  @media (min-width: 640px) {
    .filters { grid-template-columns: 1fr 1fr 1fr 1fr; align-items: end; }
    .filters > input { grid-column: 1 / -1; }
    .filters > input, .filters > select { grid-column: auto; }
  }
  section { margin-top: 20px; }
  h2 {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin: 0;
    padding: 0 2px 6px;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--muted);
    border-bottom: 1px solid var(--rule);
  }
  h2 span:first-child::first-letter { text-transform: uppercase; }
  .daysum { font-weight: 500; }
  ul { list-style: none; margin: 0; padding: 0; }
  li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 2px;
    border-bottom: 1px solid var(--rule);
  }
  .cat { border: none; background: none; padding: 0; border-radius: 50%; flex: none; display: inline-flex; }
  .what { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .desc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { font-size: 0.82rem; display: flex; gap: 6px; align-items: center; min-width: 0; }
  .catname, .acct { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .catname { flex: none; max-width: 60%; }
  .tag { color: var(--pending); border: 1px dashed currentColor; border-radius: 4px; padding: 0 5px; font-size: 0.75rem; }
  .amount { font-size: 1.12rem; font-weight: 600; white-space: nowrap; letter-spacing: -0.01em; }
  .in { color: var(--in); }
  li.pending .desc, li.pending .amount { color: var(--muted); font-style: italic; }
  .notice {
    position: sticky; top: 64px; z-index: 1;
    display: flex; justify-content: space-between; align-items: center; gap: 8px;
    margin: 8px 0 0; padding: 8px 8px 8px 12px; font-size: 0.9rem;
    background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
  }
  .notice button { border: none; background: none; padding: 2px 6px; color: var(--muted); }
  .empty { text-align: center; padding: 48px 0; color: var(--muted); }
  .more { display: block; margin: 24px auto 0; }
</style>
