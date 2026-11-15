<script setup lang="ts">
/**
 * Site header: one bar on every width.
 *
 * Product mark at the left, text navigation beside it, and the account control
 * at the right. Below 880px the text navigation collapses into a "Menu" button
 * that opens a full-width panel under the header. Both disclosures close on a
 * route change, on Escape, and on a click outside them.
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppIcon from "@/components/ui/AppIcon.vue";
import { useSessionStore } from "@/stores/session";
import { NAVIGASI } from "./tujuan";

const route = useRoute();
const router = useRouter();
const session = useSessionStore();

const menuOpen = ref(false);
const akunOpen = ref(false);
const menuButton = ref<HTMLButtonElement | null>(null);
const akunButton = ref<HTMLButtonElement | null>(null);
const headerEl = ref<HTMLElement | null>(null);

function aktif(path: string) {
  if (path === "/transaksi/baru") return route.path === path;
  return route.path === path || route.path.startsWith(`${path}/`);
}

function tutupSemua(fokus?: HTMLButtonElement | null) {
  const adaYangTerbuka = menuOpen.value || akunOpen.value;
  menuOpen.value = false;
  akunOpen.value = false;
  if (adaYangTerbuka && fokus) fokus.focus();
}

function toggleMenu() {
  akunOpen.value = false;
  menuOpen.value = !menuOpen.value;
}

function toggleAkun() {
  menuOpen.value = false;
  akunOpen.value = !akunOpen.value;
}

function onKey(e: KeyboardEvent) {
  if (e.key !== "Escape") return;
  if (menuOpen.value) tutupSemua(menuButton.value);
  else if (akunOpen.value) tutupSemua(akunButton.value);
}

function onOutside(e: MouseEvent) {
  if (!headerEl.value) return;
  if (!headerEl.value.contains(e.target as Node)) tutupSemua();
}

// A route change means the user has arrived somewhere, so any open panel is stale.
watch(
  () => route.fullPath,
  () => tutupSemua(),
);

onMounted(() => {
  document.addEventListener("keydown", onKey);
  document.addEventListener("click", onOutside);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey);
  document.removeEventListener("click", onOutside);
});

async function keluar() {
  tutupSemua();
  await session.keluar();
  await router.push("/");
}

function ubahTema() {
  session.toggleTheme();
  tutupSemua();
}
</script>

<template>
  <header ref="headerEl" class="site-header">
    <div class="inner">
      <RouterLink to="/dasbor" class="brand" aria-label="KlasifiPajak, beranda workspace">
        <span class="mark" aria-hidden="true">K</span>
        <span class="word">KlasifiPajak</span>
      </RouterLink>

      <nav class="nav" aria-label="Navigasi utama">
        <RouterLink
          v-for="t in NAVIGASI"
          :key="t.to"
          :to="t.to"
          class="link"
          :class="{ on: aktif(t.to), act: t.action }"
          :aria-current="aktif(t.to) ? 'page' : undefined"
        >
          {{ t.label }}
        </RouterLink>
      </nav>

      <div class="end">
        <button
          ref="menuButton"
          class="menu-btn"
          type="button"
          aria-controls="menu-utama"
          :aria-expanded="menuOpen ? 'true' : 'false'"
          @click="toggleMenu"
        >
          <AppIcon name="menu" :size="20" :stroke-width="1.8" />
          <span>Menu</span>
        </button>

        <div class="akun">
          <button
            ref="akunButton"
            class="avatar"
            type="button"
            aria-controls="menu-akun"
            :aria-expanded="akunOpen ? 'true' : 'false'"
            :aria-label="`Akun ${session.tampilanNama || ''}`.trim()"
            @click="toggleAkun"
          >
            {{ session.inisial }}
          </button>

          <div v-show="akunOpen" id="menu-akun" class="pop" aria-label="Menu akun">
            <p class="who">
              <strong>{{ session.tampilanNama }}</strong>
              <span>{{ session.user?.email ?? "" }}</span>
            </p>
            <RouterLink to="/profil" class="item" @click="tutupSemua()">
              <AppIcon name="profil" :size="18" :stroke-width="1.7" />
              Profil
            </RouterLink>
            <RouterLink to="/kuota" class="item" @click="tutupSemua()">
              <AppIcon name="kuota" :size="18" :stroke-width="1.7" />
              Kuota
            </RouterLink>
            <button class="item" type="button" @click="ubahTema">
              <AppIcon
                :name="session.theme === 'dark' ? 'matahari' : 'bulan'"
                :size="18"
                :stroke-width="1.7"
              />
              {{ session.theme === "dark" ? "Tampilan terang" : "Tampilan gelap" }}
            </button>
            <div class="sep" />
            <button class="item" type="button" @click="keluar">
              <AppIcon name="logout" :size="18" :stroke-width="1.7" />
              Keluar
            </button>
          </div>
        </div>
      </div>
    </div>

    <div id="menu-utama" v-show="menuOpen" class="drawer">
      <nav class="drawer-nav" aria-label="Menu utama">
        <RouterLink
          v-for="t in NAVIGASI"
          :key="t.to"
          :to="t.to"
          class="drawer-link"
          :class="{ on: aktif(t.to) }"
          :aria-current="aktif(t.to) ? 'page' : undefined"
          @click="tutupSemua()"
        >
          {{ t.label }}
        </RouterLink>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.site-header {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--surface);
  border-bottom: 1px solid var(--hairline);
}

.inner {
  display: flex;
  align-items: center;
  gap: var(--s-6);
  height: var(--header-h);
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding-inline: var(--gutter);
}

@media (min-width: 880px) {
  .inner {
    padding-inline: var(--s-6);
  }
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  flex: none;
  color: var(--ink);
  border-radius: var(--r-md);
}

.mark {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--r-md);
  background: var(--accent);
  color: var(--accent-ink);
  font: 600 0.9375rem/1 var(--font-sans);
}

.word {
  font: var(--t-title-3);
  white-space: nowrap;
}

/* Text navigation. Hidden under 880px, where the Menu button takes over. */
.nav {
  display: none;
  align-items: center;
  gap: var(--s-1);
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.link {
  display: inline-flex;
  align-items: center;
  height: 2.25rem;
  padding-inline: var(--s-3);
  border-radius: var(--r-md);
  font: var(--t-label);
  color: var(--ink-2);
  white-space: nowrap;
  transition:
    color var(--t-fast) var(--ease-out-soft),
    background-color var(--t-fast) var(--ease-out-soft);
}

.link:hover {
  color: var(--ink);
  background: var(--surface-sunken);
}

.link.on {
  color: var(--accent-soft-ink);
  background: var(--accent-soft);
  font-weight: 600;
}

.link.act {
  color: var(--accent);
}

.end {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-left: auto;
  flex: none;
}

.menu-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  height: 2.75rem;
  padding-inline: var(--s-3);
  border: 1px solid var(--field-line);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--ink);
  font: var(--t-label);
}

.menu-btn:hover {
  background: var(--surface-sunken);
}

.akun {
  position: relative;
}

.avatar {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--r-full);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
  font: 600 0.875rem/1 var(--font-sans);
}

.avatar:hover {
  background: var(--accent-line);
}

.pop {
  position: absolute;
  right: 0;
  top: calc(100% + var(--s-2));
  width: 16rem;
  padding: var(--s-2);
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
}

.who {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: var(--s-2) var(--s-3) var(--s-3);
}

.who strong {
  font: var(--t-label);
}

.who span {
  font: var(--t-body-sm);
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sep {
  height: 1px;
  background: var(--hairline);
  margin: var(--s-1) 0;
}

.item {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  width: 100%;
  min-height: 2.75rem;
  padding: 0 var(--s-3);
  border-radius: var(--r-sm);
  font: var(--t-label);
  color: var(--ink-2);
  text-align: left;
}

.item:hover {
  background: var(--surface-sunken);
  color: var(--ink);
}

/* Mobile panel: full width, directly under the header. */
.drawer {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  background: var(--surface);
  border-bottom: 1px solid var(--hairline);
  box-shadow: var(--shadow-2);
}

.drawer-nav {
  display: flex;
  flex-direction: column;
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding: var(--s-2) var(--gutter) var(--s-4);
}

.drawer-link {
  display: flex;
  align-items: center;
  min-height: 3rem;
  padding-inline: var(--s-3);
  border-radius: var(--r-md);
  font: var(--t-body);
  color: var(--ink);
}

.drawer-link:hover {
  background: var(--surface-sunken);
}

.drawer-link.on {
  color: var(--accent-soft-ink);
  background: var(--accent-soft);
  font-weight: 600;
}

@media (min-width: 880px) {
  .nav {
    display: flex;
  }

  .menu-btn {
    display: none;
  }

  /* The panel can only be open below 880px; if the window widens while it is
     open, it must not linger. */
  .drawer {
    display: none !important;
  }
}
</style>
