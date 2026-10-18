<script setup lang="ts">
/**
 * Bottom tab bar, below 768px.
 *
 * Translucent so the ledger scrolls underneath it. The content area carries a
 * bottom fade where the bar overlaps, rather than a divider line, so the bar
 * reads as a layer over the page.
 */
import { useRoute } from "vue-router";
import AppIcon from "@/components/ui/AppIcon.vue";
import { TUJUAN } from "./tujuan";

const route = useRoute();

function aktif(path: string) {
  if (path === "/transaksi/baru") return route.path === path;
  return route.path === path || route.path.startsWith(`${path}/`);
}
</script>

<template>
  <nav class="tabs" aria-label="Navigasi utama">
    <div class="inner">
      <RouterLink
        v-for="t in TUJUAN"
        :key="t.to"
        :to="t.to"
        class="tab"
        :class="{ on: aktif(t.to), act: t.action }"
        :aria-current="aktif(t.to) ? 'page' : undefined"
      >
        <span class="glyph">
          <AppIcon :name="t.icon" :size="t.action ? 20 : 21" :stroke-width="1.75" />
        </span>
        <span class="txt">{{ t.short }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.tabs {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  display: block;
  background: var(--material-bar);
  backdrop-filter: var(--blur-bar);
  padding-bottom: var(--safe-b);
  box-shadow: 0 -0.5px 0 var(--material-bar-line);
}

.inner {
  display: flex;
  align-items: stretch;
  height: var(--tabbar-h);
  max-width: 34rem;
  margin-inline: auto;
}

.tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.125rem;
  color: var(--ink-3);
  transition: color var(--t-fast) var(--ease-out-soft);
  min-width: 0;
}

.glyph {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 1.75rem;
  border-radius: var(--r-sm);
  transition:
    background-color var(--t-base) var(--ease-out-soft),
    transform var(--t-press) var(--ease-out-soft);
}

.tab:active .glyph {
  transform: scale(0.9);
}

.txt {
  font: 500 0.625rem/1.2 var(--font-sans);
  letter-spacing: 0.01em;
}

.tab.on {
  color: var(--accent);
}

.tab.on .txt {
  font-weight: 600;
}

.tab.on .glyph {
  background: var(--accent-soft);
}

/* The entry point gets the filled treatment so it reads as the one button on
   this bar rather than a fifth destination. */
.tab.act .glyph {
  background: var(--accent);
  color: var(--accent-ink);
}

.tab.act.on {
  color: var(--ink);
}

.tab.act.on .glyph {
  background: var(--accent);
}

@media (min-width: 768px) {
  .tabs {
    display: none;
  }
}
</style>
