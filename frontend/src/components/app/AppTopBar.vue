<script setup lang="ts">
/**
 * Floating top bar.
 *
 * Title, ruleset stamp, and the account control. It floats over the content and
 * the content fades out beneath it, so no row is ever cut by a hard rule.
 */
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppIcon from "@/components/ui/AppIcon.vue";
import { tanggalPanjang } from "@/lib/format";
import { useKuotaStore } from "@/stores/kuota";
import { usePajakStore } from "@/stores/pajak";
import { useProfilStore } from "@/stores/profil";
import { useSessionStore } from "@/stores/session";

const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const profil = useProfilStore();
const pajak = usePajakStore();
const kuota = useKuotaStore();
const open = ref(false);
const stampId = computed(() => pajak.dashboard?.metadata.ruleset_id ?? "");
const stampDate = computed(() => pajak.dashboard?.metadata.effective_date ?? "");
const nama = computed(() => profil.profile?.name || session.tampilanNama);
const usaha = computed(() => profil.profile?.business_description || session.user?.email || "");

function toggle() {
  open.value = !open.value;
}

function close() {
  open.value = false;
}

async function keluar() {
  open.value = false;
  await session.keluar();
  await router.push("/");
}
</script>

<template>
  <header class="bar">
    <div class="inner">
      <div class="lead">
        <h1 class="title">{{ route.meta.title ?? "KlasifiPajak" }}</h1>
        <p class="stamp">
          <span class="hide-sm">Kertas kerja · </span>
          <template v-if="stampId && stampDate">
            ruleset <code>{{ stampId }}</code> · berlaku {{ tanggalPanjang(stampDate) }}
          </template>
          <template v-else>ruleset belum dimuat</template>
          <template v-if="kuota.labelTier"> · {{ kuota.labelTier }}</template>
        </p>
      </div>

      <div class="menu-wrap">
        <button
          class="avatar press"
          type="button"
          :aria-expanded="open"
          aria-haspopup="menu"
          aria-label="Akun"
          @click="toggle"
        >
          {{ nama.charAt(0) || "?" }}
        </button>

        <Transition name="pop">
          <div v-if="open" class="pop kp-materialize" role="menu">
            <p class="who">
              <strong>{{ nama }}</strong>
              <span>{{ usaha }}</span>
            </p>
            <div class="sep" />
            <RouterLink to="/profil" class="item" role="menuitem" @click="close">
              <AppIcon name="profil" :size="17" :stroke-width="1.7" />
              Profil dan usaha
            </RouterLink>
            <RouterLink to="/kuota" class="item" role="menuitem" @click="close">
              <AppIcon name="kuota" :size="17" :stroke-width="1.7" />
              Kuota dan langganan
            </RouterLink>
            <button
              class="item"
              role="menuitem"
              type="button"
              @click="
                session.toggleTheme();
                close();
              "
            >
              <AppIcon
                :name="session.theme === 'dark' ? 'matahari' : 'bulan'"
                :size="17"
                :stroke-width="1.7"
              />
              {{ session.theme === "dark" ? "Tampilan terang" : "Tampilan gelap" }}
            </button>
            <div class="sep" />
            <button class="item" role="menuitem" type="button" @click="keluar">
              <AppIcon name="logout" :size="17" :stroke-width="1.7" />
              Keluar
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.bar {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--material-bar);
  backdrop-filter: var(--blur-bar);
  box-shadow: 0 0.5px 0 var(--material-bar-line);
  padding-top: var(--safe-t);
}

.inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  height: var(--topbar-h);
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding-inline: var(--s-4);
}

@media (min-width: 768px) {
  .inner {
    padding-inline: var(--s-6);
    height: 3.5rem;
  }
}

@media (min-width: 1280px) {
  .inner {
    padding-inline: var(--s-10);
  }
}

.lead {
  min-width: 0;
}

.title {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (min-width: 768px) {
  .title {
    font: var(--t-title-1);
    letter-spacing: var(--track-title-1);
  }
}

.stamp {
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 0.0625rem;
}

.stamp code {
  font-family: var(--font-numeric);
  font-size: inherit;
}

.menu-wrap {
  position: relative;
  flex: none;
}

.avatar {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--r-full);
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  color: var(--ink);
  font: 600 0.8125rem/1 var(--font-sans);
}

.avatar:hover {
  background: var(--surface-raised);
}

.pop {
  position: absolute;
  right: 0;
  top: calc(100% + 0.5rem);
  /* Anchored to the trigger, so the spatial relationship is obvious. */
  transform-origin: top right;
  width: 15rem;
  padding: var(--s-2);
  background: var(--material-sheet);
  backdrop-filter: var(--blur-bar);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-3);
}

.who {
  display: flex;
  flex-direction: column;
  gap: 0.0625rem;
  padding: var(--s-2) var(--s-3) var(--s-3);
}

.who strong {
  font: var(--t-label);
  letter-spacing: var(--track-label);
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
  padding: 0.5rem var(--s-3);
  border-radius: var(--r-sm);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  text-align: left;
}

.item:hover {
  background: color-mix(in oklab, var(--ink) 6%, transparent);
  color: var(--ink);
}

.pop-enter-active,
.pop-leave-active {
  transition:
    opacity var(--t-fast) var(--ease-out-soft),
    transform var(--t-fast) var(--ease-out-soft);
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .pop-enter-from,
  .pop-leave-to {
    transform: none;
  }
}
</style>
