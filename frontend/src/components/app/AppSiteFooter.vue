<script setup lang="ts">
/** Site footer: product name, the working-paper disclaimer, and two account links. */
</script>

<template>
  <footer class="site-footer">
    <div class="inner">
      <div class="who">
        <p class="name">KlasifiPajak</p>
        <p class="note">Kertas kerja, bukan SPT dan bukan pelaporan ke DJP.</p>
      </div>
      <nav class="links" aria-label="Tautan kaki">
        <RouterLink to="/profil">Profil</RouterLink>
        <RouterLink to="/kuota">Kuota</RouterLink>
      </nav>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: auto;
  background: var(--surface);
  border-top: 1px solid var(--hairline);
}

.inner {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding: var(--s-6) var(--gutter);
}

@media (min-width: 880px) {
  .inner {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: var(--s-6);
  }
}

.name {
  font: var(--t-label);
}

.note {
  font: var(--t-body-sm);
  color: var(--ink-3);
  margin-top: var(--s-1);
}

.links {
  display: flex;
  gap: var(--s-5);
  font: var(--t-label);
}

.links a {
  color: var(--ink-2);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.links a:hover {
  color: var(--ink);
}
</style>
