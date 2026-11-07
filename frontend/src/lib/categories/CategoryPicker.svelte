<script lang="ts">
  import CategoryIcon from './CategoryIcon.svelte';
  import { categories } from './store.svelte';

  let {
    title,
    current,
    onselect,
    onclose
  }: {
    title: string;
    current: number | null;
    onselect: (id: number | null) => void;
    onclose: () => void;
  } = $props();

  let dialog: HTMLDialogElement;
  let search: HTMLInputElement;
  let q = $state('');

  const filtered = $derived.by(() => {
    const needle = q.trim().toLocaleLowerCase('sv');
    if (!needle) return categories.groups;
    return categories.groups
      .map(({ group, children }) => {
        const groupHit = group.name.toLocaleLowerCase('sv').includes(needle);
        return {
          group,
          children: groupHit ? children : children.filter((c) => c.name.toLocaleLowerCase('sv').includes(needle))
        };
      })
      .filter((g) => g.children.length);
  });

  $effect(() => {
    dialog.showModal();
    // Focusing the search on a phone would pop up the keyboard over the list
    if (matchMedia('(pointer: fine)').matches) search.focus();
  });
</script>

<dialog bind:this={dialog} onclose={onclose} onclick={(e) => e.target === dialog && dialog.close()}>
  <div class="sheet">
    <header>
      <div class="title">
        <span class="muted small">Välj kategori för</span>
        <strong>{title}</strong>
      </div>
      <button type="button" class="close" aria-label="Stäng" onclick={() => dialog.close()}>✕</button>
    </header>
    <input type="search" placeholder="Sök kategori" aria-label="Sök kategori" bind:value={q} bind:this={search} />
    <div class="list">
      {#each filtered as { group, children } (group.id)}
        <section>
          <h3><CategoryIcon icon={group.icon} color={group.color} size={22} /> {group.name}</h3>
          <div class="options">
            {#each children as c (c.id)}
              <button type="button" class="option" class:selected={c.id === current} onclick={() => onselect(c.id)}>
                <CategoryIcon icon={c.icon} color={c.color} size={28} />
                <span>{c.name}</span>
              </button>
            {/each}
          </div>
        </section>
      {:else}
        <p class="muted">Ingen kategori matchar.</p>
      {/each}
    </div>
    {#if current !== null}
      <button type="button" class="clear" onclick={() => onselect(null)}>Ta bort kategori</button>
    {/if}
  </div>
</dialog>

<style>
  dialog {
    padding: 0;
    border: 1px solid var(--rule);
    border-radius: 14px;
    background: var(--bg);
    color: var(--ink);
    width: min(560px, calc(100vw - 2 * var(--gutter)));
    max-height: min(720px, calc(100dvh - 48px));
  }
  dialog::backdrop { background: rgb(0 0 0 / 0.4); }
  .sheet { display: flex; flex-direction: column; gap: 10px; padding: 14px var(--gutter) 16px; max-height: inherit; }
  header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .title { display: flex; flex-direction: column; min-width: 0; }
  .title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .small { font-size: 0.8rem; }
  .close { border: none; background: none; padding: 4px 8px; color: var(--muted); }
  input { width: 100%; }
  .list { overflow-y: auto; min-height: 0; flex: 1; }
  section + section { margin-top: 14px; }
  h3 {
    display: flex; align-items: center; gap: 8px;
    margin: 0 0 6px; font-size: 0.85rem; font-weight: 600; color: var(--muted);
  }
  .options { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }
  .option {
    display: flex; align-items: center; gap: 10px; text-align: left;
    padding: 6px 10px 6px 6px; border-radius: 10px; min-width: 0;
  }
  .option span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .option.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
  .clear { align-self: flex-start; color: var(--danger); }
  @media (max-width: 520px) {
    dialog {
      width: 100vw; max-width: 100vw; margin: auto 0 0; border-radius: 14px 14px 0 0;
      max-height: 85dvh;
    }
    .sheet { padding-bottom: calc(16px + env(safe-area-inset-bottom)); }
  }
</style>
