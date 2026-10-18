<script setup lang="ts">
/**
 * Left navigation: a labelled sidebar from 1280px, an icon rail from 768px.
 * Below 768px this is not rendered at all and the tab bar takes over.
 */
import { useRoute } from "vue-router";
import AppIcon from "@/components/ui/AppIcon.vue";
import { TUJUAN, TUJUAN_SEKUNDER } from "./tujuan";

const route = useRoute();

function aktif(path: string) {
  if (path === "/transaksi/baru") return route.path === path;
  return route.path === path || route.path.startsWith(`${path}/`);
}
</script>

<template>
  <aside class="side" aria-label="Navigasi utama">
    <RouterLink to="/dasbor" class="brand">
      <span class="mark" aria-hidden="true">K</span>
      <span class="word">KlasifiPajak</span>
    </RouterLink>

    <nav class="nav">
      <RouterLink
        v-for="t in TUJUAN"
        :key="t.to"
        :to="t.to"
        class="item"
        :class="{ on: aktif(t.to), act: t.action }"
        :title="t.label"
        :aria-label="t.label"
        :aria-current="aktif(t.to) ? 'page' : undefined"
      >
        <span class="glyph"><AppIcon :name="t.icon" :size="19" :stroke-width="1.7" /></span>
        <span class="label">{{ t.short }}</span>
      </RouterLink>
    </nav>

    <nav class="nav secondary">
      <RouterLink
        v-for="t in TUJUAN_SEKUNDER"
        :key="t.to"
        :to="t.to"
        class="item"
        :class="{ on: aktif(t.to) }"
        :title="t.label"
        :aria-label="t.label"
        :aria-current="aktif(t.to) ? 'page' : undefined"
      >
        <span class="glyph"><AppIcon :name="t.icon" :size="19" :stroke-width="1.7" /></span>
        <span class="label">{{ t.short ?? t.label }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.side {
  display: none;
  flex-direction: column;
  gap: var(--s-2);
  width: var(--rail-w);
  flex: none;
  padding: var(--s-4) var(--s-3);
  position: sticky;
  top: 0;
  height: 100svh;
  /* Chrome, not a wall: content on the right reads through it. */
  background: var(--material-bar);
  backdrop-filter: var(--blur-bar);
  border-right: 1px solid var(--material-bar-line);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-1) var(--s-2) var(--s-4);
  margin-bottom: var(--s-2);
}

.mark {
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  flex: none;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--accent-ink);
  font: 600 0.875rem/1 var(--font-sans);
  letter-spacing: 0;
}

.word {
  display: none;
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  white-space: nowrap;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.secondary {
  margin-top: auto;
  padding-top: var(--s-4);
  border-top: 1px solid var(--hairline);
}

.item {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  height: 2.5rem;
  padding-inline: var(--s-2);
  border-radius: var(--r-md);
  color: var(--ink-2);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  transition:
    background-color var(--t-fast) var(--ease-out-soft),
    color var(--t-fast) var(--ease-out-soft);
}

.label {
  display: none;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.glyph {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: var(--r-sm);
  transition: background-color var(--t-fast) var(--ease-out-soft);
}

.item:hover {
  background: color-mix(in oklab, var(--ink) 5%, transparent);
  color: var(--ink);
}

.item.on {
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
  font-weight: 600;
}

.item.on .glyph {
  background: color-mix(in oklab, var(--accent) 16%, transparent);
}

/* Rail: icon over a 10px label, so the destination is nameable, not a guess. */
@media (min-width: 768px) {
  .side {
    display: flex;
  }

  .item {
    flex-direction: column;
    gap: 0.125rem;
    height: auto;
    padding: var(--s-2) 0;
  }

  .label {
    display: block;
    font-size: 0.625rem;
    letter-spacing: var(--track-caption);
    color: inherit;
    opacity: 0.78;
    padding-inline: 0.25rem;
  }

  .item.on .label {
    opacity: 1;
  }
}

/* Sidebar: full labels, wider rail. */
@media (min-width: 1280px) {
  .side {
    width: var(--sidebar-w);
    padding: var(--s-5) var(--s-3);
  }

  .brand {
    padding-inline: var(--s-2);
  }

  .word {
    display: block;
  }

  .item {
    flex-direction: row;
    gap: var(--s-2);
    height: 2.5rem;
    padding: 0 var(--s-3);
  }

  .label {
    font-size: 0.8125rem;
    letter-spacing: var(--track-label);
  }

  /* A primary action in a navigation list competes with the navigation. In the
     sidebar it earns a slot; on the phone it already has the tab bar. */
  .item.act {
    display: none;
  }
}
</style>
