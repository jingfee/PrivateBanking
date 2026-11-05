<script lang="ts">
  import '../app.css';
  import { page } from '$app/state';
  let { children } = $props();
</script>

<header>
  <a class="brand" href="/">Kassabok</a>
  <nav>
    <a href="/" aria-current={page.url.pathname === '/' ? 'page' : undefined}>Transaktioner</a>
    <a href="/accounts" aria-current={page.url.pathname.startsWith('/accounts') ? 'page' : undefined}>Konton</a>
  </nav>
</header>

<main>
  {@render children()}
</main>

<style>
  header {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    max-width: 760px;
    margin: 0 auto;
    padding: calc(12px + env(safe-area-inset-top)) var(--gutter) 12px;
    background: var(--bg);
    border-bottom: 1px solid var(--rule);
  }
  .brand { font-weight: 700; font-size: 1.15rem; color: var(--ink); text-decoration: none; letter-spacing: -0.01em; }
  nav { display: flex; gap: 16px; }
  nav a { color: var(--muted); text-decoration: none; padding: 4px 0; }
  nav a[aria-current='page'] { color: var(--ink); box-shadow: inset 0 -2px 0 var(--accent); }
  main { max-width: 760px; margin: 0 auto; padding: 16px var(--gutter) 48px; }
</style>
