<script lang="ts">
  import { page } from '$app/state';
  import { api, formatDate, type Account, type Bank } from '$lib/api';

  let accounts = $state<Account[]>([]);
  let banks = $state<Bank[]>([]);
  let bank = $state('');
  let error = $state('');
  let busy = $state<'' | 'connect' | 'sync'>('');
  let message = $state('');
  let showConnect = $state(false);

  const DAY = 86400000;
  const daysLeft = (iso: string | null) => (iso ? Math.ceil((new Date(iso).getTime() - Date.now()) / DAY) : null);

  const groups = $derived.by(() => {
    const m = new Map<string, Account[]>();
    for (const a of accounts) m.set(a.aspsp, [...(m.get(a.aspsp) ?? []), a]);
    return [...m.entries()];
  });

  async function loadAccounts() {
    try {
      accounts = await api.accounts();
    } catch (e) {
      error = `Kunde inte hämta konton: ${(e as Error).message}`;
    }
  }

  async function openConnect() {
    showConnect = true;
    if (banks.length) return;
    try {
      banks = await api.banks();
    } catch (e) {
      error = `Kunde inte hämta banklistan: ${(e as Error).message}`;
    }
  }

  async function connect() {
    busy = 'connect';
    error = '';
    try {
      const { url } = await api.connect(bank);
      location.href = url;
    } catch (e) {
      error = `Kunde inte starta kopplingen: ${(e as Error).message}`;
      busy = '';
    }
  }

  async function sync() {
    busy = 'sync';
    error = '';
    message = '';
    try {
      const runs = (await api.sync()) as { inserted: number; error: string | null }[];
      const inserted = runs.reduce((s, r) => s + r.inserted, 0);
      const failed = runs.filter((r) => r.error).length;
      message = `Synkat. ${inserted} nya transaktioner${failed ? `, ${failed} konton misslyckades` : ''}.`;
      await loadAccounts();
    } catch (e) {
      error = `Synken misslyckades: ${(e as Error).message}`;
    } finally {
      busy = '';
    }
  }

  $effect(() => {
    loadAccounts();
  });
</script>

{#if page.url.searchParams.has('connected')}
  <p class="notice">Banken är kopplad och transaktionerna är hämtade.</p>
{:else if page.url.searchParams.has('error')}
  <p class="notice error">Kopplingen avbröts eller misslyckades. Försök igen.</p>
{/if}

<div class="actions">
  <button class="primary" onclick={openConnect}>Koppla bank</button>
  <button onclick={sync} disabled={busy === 'sync' || accounts.length === 0}>
    {busy === 'sync' ? 'Synkar…' : 'Synka nu'}
  </button>
</div>

{#if showConnect}
  <form class="connect" onsubmit={(e) => { e.preventDefault(); connect(); }}>
    <select aria-label="Bank" bind:value={bank} required>
      <option value="" disabled>Välj bank</option>
      {#each banks as b (b.name)}
        <option value={b.name}>{b.name}</option>
      {/each}
    </select>
    <button class="primary" disabled={!bank || busy === 'connect'}>
      {busy === 'connect' ? 'Öppnar BankID…' : 'Fortsätt till BankID'}
    </button>
  </form>
{/if}

{#if message}<p class="muted">{message}</p>{/if}
{#if error}<p class="error">{error}</p>{/if}

{#if accounts.length === 0 && !error}
  <p class="empty">Inga konton kopplade. Välj Koppla bank och logga in med BankID.</p>
{/if}

{#each groups as [aspsp, list] (aspsp)}
  {@const left = daysLeft(list[0].valid_until)}
  {@const status = list[0].connection_status}
  <section>
    <h2>{aspsp}</h2>
    <p class="consent" class:warn={status !== 'active' || (left !== null && left <= 14)}>
      {#if status === 'expired' || (left !== null && left <= 0)}
        Samtycket har gått ut. Koppla banken igen för att fortsätta hämta.
      {:else if status === 'error'}
        Kopplingen fungerar inte. Koppla banken igen.
      {:else if left !== null}
        Samtycket gäller till {formatDate(list[0].valid_until)} ({left} dagar kvar).
      {/if}
    </p>
    <ul>
      {#each list as a (a.id)}
        <li>
          <div>
            <div>{a.name ?? 'Konto'}</div>
            <div class="muted small">{a.identifier ?? ''}</div>
          </div>
          <div class="right small muted">
            <div class="num">{a.transaction_count} transaktioner</div>
            <div>Synkat {a.last_synced_at ? new Date(a.last_synced_at).toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' }) : 'aldrig'}</div>
            {#if a.last_error}<div class="error">Senaste synken misslyckades</div>{/if}
          </div>
        </li>
      {/each}
    </ul>
  </section>
{/each}

<style>
  .actions, .connect { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .connect select { flex: 1; min-width: 200px; }
  .notice { padding: 10px 12px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--rule); }
  section { margin-top: 24px; }
  h2 { font-size: 1.05rem; margin: 0 0 2px; }
  .consent { margin: 0 0 8px; font-size: 0.88rem; color: var(--muted); }
  .consent.warn { color: var(--pending); font-weight: 600; }
  ul { list-style: none; margin: 0; padding: 0; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); }
  li { display: flex; justify-content: space-between; gap: 12px; padding: 12px 14px; }
  li + li { border-top: 1px solid var(--rule); }
  .right { text-align: right; }
  .small { font-size: 0.85rem; }
  .empty { color: var(--muted); padding: 32px 0; text-align: center; }
</style>
