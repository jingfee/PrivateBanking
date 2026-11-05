<script lang="ts">
  import { api, formatAmount, formatDay, type Account, type Transaction } from '$lib/api';

  const PAGE = 100;
  let items = $state<Transaction[]>([]);
  let total = $state(0);
  let accounts = $state<Account[]>([]);
  let q = $state('');
  let account = $state('');
  let from = $state('');
  let to = $state('');
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
      const res = await api.transactions({ q, account, from, to, limit: PAGE, offset: append ? items.length : 0 });
      items = append ? [...items, ...res.items] : res.items;
      total = res.total;
    } catch (e) {
      error = `Kunde inte hämta transaktioner: ${(e as Error).message}`;
    } finally {
      loading = false;
    }
  }

  let timer: ReturnType<typeof setTimeout>;
  function search() {
    clearTimeout(timer);
    timer = setTimeout(() => load(), 250);
  }

  $effect(() => {
    api.accounts().then((a) => (accounts = a)).catch(() => {});
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
  <label>Från <input type="date" bind:value={from} onchange={() => load()} /></label>
  <label>Till <input type="date" bind:value={to} onchange={() => load()} /></label>
</form>

{#if error}
  <p class="error">{error}</p>
{:else if !loading && items.length === 0}
  <div class="empty">
    {#if q || account || from || to}
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
        <li class:pending={t.status === 'PDNG'}>
          <div class="what">
            <span class="desc">{t.description || 'Okänd transaktion'}</span>
            <span class="meta muted">
              {t.account}{#if t.status === 'PDNG'}<span class="tag">Reserverad</span>{/if}
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
    .filters { grid-template-columns: 2fr 1.2fr 1fr 1fr; align-items: end; }
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
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding: 10px 2px;
    border-bottom: 1px solid var(--rule);
  }
  .what { display: flex; flex-direction: column; min-width: 0; }
  .desc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { font-size: 0.82rem; display: flex; gap: 8px; align-items: center; }
  .tag { color: var(--pending); border: 1px dashed currentColor; border-radius: 4px; padding: 0 5px; font-size: 0.75rem; }
  .amount { font-size: 1.12rem; font-weight: 600; white-space: nowrap; letter-spacing: -0.01em; }
  .in { color: var(--in); }
  li.pending .desc, li.pending .amount { color: var(--muted); font-style: italic; }
  .empty { text-align: center; padding: 48px 0; color: var(--muted); }
  .more { display: block; margin: 24px auto 0; }
</style>
