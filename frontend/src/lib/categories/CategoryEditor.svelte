<script lang="ts" module>
  export const PALETTE = [
    'blue', 'sky', 'teal', 'green', 'lime', 'amber', 'orange', 'red', 'pink', 'purple', 'slate', 'brown', 'gray'
  ] as const;

  export const KINDS = [
    { value: 'expense', label: 'Utgift', hint: 'Räknas som en kostnad' },
    { value: 'income', label: 'Inkomst', hint: 'Räknas som en inkomst' },
    { value: 'reimbursement', label: 'Ersättning', hint: 'Pengar tillbaka för delade utgifter, minskar dina kostnader' },
    { value: 'transfer', label: 'Överföring', hint: 'Räknas varken som utgift eller inkomst' }
  ] as const;
</script>

<script lang="ts">
  import { untrack } from 'svelte';
  import type { Category, CategoryInput } from '$lib/api';
  import CategoryIcon from './CategoryIcon.svelte';
  import { ICONS, ICON_NAMES } from './icons';

  let {
    category = null,
    parent = null,
    affected = 0,
    onsave,
    ondelete,
    onclose
  }: {
    /** the category to edit, or null to create a new one */
    category?: Category | null;
    /** the top-level category a subcategory belongs to (also when creating one) */
    parent?: Category | null;
    /** transactions that lose their category on delete, subcategories included */
    affected?: number;
    onsave: (input: CategoryInput) => Promise<void>;
    ondelete?: () => Promise<void>;
    onclose: () => void;
  } = $props();

  // Copies of the props: the form edits these, the saved category only changes on save
  const initial = untrack(() => category);
  let name = $state(initial?.name ?? '');
  let icon = $state(initial?.icon ?? 'tag');
  let color = $state(initial?.color ?? 'blue');
  let kind = $state<Category['kind']>(initial?.kind ?? 'expense');
  let busy = $state(false);
  let error = $state('');
  let confirmDelete = $state(false);

  const isSub = $derived(parent !== null);
  const shownColor = $derived(isSub ? (parent?.color ?? 'gray') : color);

  let dialog: HTMLDialogElement;
  $effect(() => {
    dialog.showModal();
  });

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    error = '';
    try {
      await onsave(isSub ? { name, icon } : { name, icon, color, kind });
      dialog.close();
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }

  async function remove() {
    if (!ondelete) return;
    busy = true;
    error = '';
    try {
      await ondelete();
      dialog.close();
    } catch (err) {
      error = (err as Error).message;
      busy = false;
    }
  }
</script>

<dialog bind:this={dialog} onclose={onclose}>
  <form class="sheet" onsubmit={save}>
    <header>
      <CategoryIcon {icon} color={shownColor} size={40} />
      <div class="title">
        <strong>{category ? 'Redigera kategori' : isSub ? 'Ny underkategori' : 'Ny huvudkategori'}</strong>
        {#if parent}<span class="muted small">i {parent.name}</span>{/if}
      </div>
      <button type="button" class="close" aria-label="Stäng" onclick={() => dialog.close()}>✕</button>
    </header>

    <div class="body">
      <label class="field">
        <span>Namn</span>
        <input bind:value={name} required maxlength="100" />
      </label>

      {#if !isSub}
        <fieldset>
          <legend>Typ</legend>
          <div class="kinds">
            {#each KINDS as k (k.value)}
              <label class="kind" class:selected={kind === k.value}>
                <input type="radio" name="kind" value={k.value} bind:group={kind} />
                <span class="kind-label">{k.label}</span>
                <span class="muted small">{k.hint}</span>
              </label>
            {/each}
          </div>
          {#if category}<p class="muted small">Underkategorierna får samma typ.</p>{/if}
        </fieldset>

        <fieldset>
          <legend>Färg</legend>
          <div class="swatches">
            {#each PALETTE as c (c)}
              <label class="swatch" style:--c="var(--cat-{c})" title={c}>
                <input type="radio" name="color" value={c} bind:group={color} aria-label={c} />
              </label>
            {/each}
          </div>
          <p class="muted small">Underkategorierna får samma färg.</p>
        </fieldset>
      {/if}

      <fieldset>
        <legend>Ikon</legend>
        <div class="icons">
          {#each ICON_NAMES as name (name)}
            {@const Icon = ICONS[name]}
            <label class="icon" class:selected={icon === name} title={name}>
              <input type="radio" name="icon" value={name} bind:group={icon} aria-label={name} />
              {#if icon === name}
                <CategoryIcon icon={name} color={shownColor} size={36} />
              {:else}
                <span class="plain"><Icon size={20} strokeWidth={2} /></span>
              {/if}
            </label>
          {/each}
        </div>
      </fieldset>

      {#if error}<p class="error">{error}</p>{/if}
    </div>

    <footer>
      {#if category && ondelete}
        {#if confirmDelete}
          <div class="confirm">
            <span class="small">
              {#if affected}
                {affected} {affected === 1 ? 'transaktion' : 'transaktioner'} blir okategoriserade och
                kategoriseras om automatiskt.
              {/if}
              {#if !isSub}Underkategorierna tas också bort.{/if}
            </span>
            <strong class="small">Ta bort {category.name}?</strong>
            <button type="button" class="danger" disabled={busy} onclick={remove}>Ta bort</button>
            <button type="button" onclick={() => (confirmDelete = false)}>Avbryt</button>
          </div>
        {:else}
          <button type="button" class="link-danger" onclick={() => (confirmDelete = true)}>Ta bort kategori</button>
        {/if}
      {/if}
      {#if !confirmDelete}
        <button class="primary" disabled={busy || !name.trim()}>{busy ? 'Sparar…' : 'Spara'}</button>
      {/if}
    </footer>
  </form>
</dialog>

<style>
  dialog {
    padding: 0;
    border: 1px solid var(--rule);
    border-radius: 14px;
    background: var(--bg);
    color: var(--ink);
    width: min(560px, calc(100vw - 2 * var(--gutter)));
    max-height: min(760px, calc(100dvh - 48px));
  }
  dialog::backdrop { background: rgb(0 0 0 / 0.4); }
  .sheet { display: flex; flex-direction: column; max-height: inherit; }
  header { display: flex; align-items: center; gap: 12px; padding: 14px var(--gutter) 10px; }
  .title { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .close { border: none; background: none; padding: 4px 8px; color: var(--muted); align-self: flex-start; }
  .body { overflow-y: auto; padding: 4px var(--gutter) 12px; display: flex; flex-direction: column; gap: 16px; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field span, legend { font-size: 0.85rem; font-weight: 600; color: var(--muted); }
  fieldset { border: none; margin: 0; padding: 0; min-width: 0; }
  legend { padding: 0; margin-bottom: 6px; }
  .small { font-size: 0.8rem; }
  fieldset > p { margin: 6px 0 0; }
  input[type='radio'] { position: absolute; opacity: 0; width: 1px; height: 1px; }

  .kinds { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }
  .kind {
    position: relative; display: flex; flex-direction: column; gap: 2px; cursor: pointer;
    padding: 8px 10px; border: 1px solid var(--rule); border-radius: 10px; background: var(--surface);
  }
  .kind-label { font-weight: 600; }
  .kind.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }

  .swatches { display: flex; flex-wrap: wrap; gap: 8px; }
  .swatch {
    position: relative; width: 32px; height: 32px; border-radius: 50%; cursor: pointer;
    background: var(--c); box-shadow: 0 0 0 2px var(--bg);
  }
  .swatch:has(input:checked) { box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--c); }

  .icons { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 4px; }
  .icon {
    position: relative; display: grid; place-items: center; padding: 3px; cursor: pointer;
    border-radius: 10px; border: 1px solid transparent;
  }
  .icon.selected { border-color: var(--accent); background: var(--surface); }
  .plain { display: grid; place-items: center; width: 36px; height: 36px; color: var(--muted); }
  .icon:hover .plain { color: var(--ink); }
  label:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }

  footer {
    display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 12px var(--gutter) 14px; border-top: 1px solid var(--rule);
  }
  footer .primary { margin-left: auto; }
  .confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; flex: 1; }
  .confirm span, .confirm strong { flex-basis: 100%; }
  .confirm span:empty { display: none; }
  .danger { background: var(--danger); border-color: var(--danger); color: var(--bg); font-weight: 600; }
  .link-danger { border: none; background: none; padding: 8px 0; color: var(--danger); }
  @media (max-width: 520px) {
    dialog { width: 100vw; max-width: 100vw; margin: auto 0 0; border-radius: 14px 14px 0 0; max-height: 92dvh; }
    footer { padding-bottom: calc(14px + env(safe-area-inset-bottom)); }
  }
</style>
