<script lang="ts">
  import { ICONS } from './icons';

  let { icon, color, size = 32 }: { icon: string | null | undefined; color?: string | null; size?: number } =
    $props();

  const Icon = $derived(ICONS[icon ?? ''] ?? ICONS.tag);
</script>

<span
  class="bubble"
  class:none={!color}
  style:--c={color ? `var(--cat-${color})` : 'var(--muted)'}
  style:width="{size}px"
  style:height="{size}px"
>
  <Icon size={Math.round(size * 0.55)} strokeWidth={2} />
</span>

<style>
  .bubble {
    display: inline-grid;
    place-items: center;
    flex: none;
    border-radius: 50%;
    color: var(--c);
    background: color-mix(in srgb, var(--c) 16%, var(--surface));
  }
  .none {
    background: transparent;
    border: 1.5px dashed var(--rule);
  }
</style>
