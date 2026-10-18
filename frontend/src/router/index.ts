import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { useSessionStore } from "@/stores/session";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "landing",
    component: () => import("@/pages/LandingPage.vue"),
    meta: { bare: true },
  },
  {
    path: "/masuk",
    name: "masuk",
    component: () => import("@/pages/MasukPage.vue"),
    meta: { bare: true },
  },
  {
    path: "/atur-ulang",
    name: "atur-ulang",
    component: () => import("@/pages/AturUlangPage.vue"),
    meta: { bare: true },
  },
  {
    path: "/dasbor",
    name: "dasbor",
    component: () => import("@/pages/DasborPage.vue"),
    meta: { title: "Pajak" },
  },
  {
    path: "/transaksi",
    name: "transaksi",
    component: () => import("@/pages/TransaksiPage.vue"),
    meta: { title: "Transaksi" },
  },
  {
    path: "/transaksi/baru",
    name: "transaksi-baru",
    component: () => import("@/pages/TransaksiBaruPage.vue"),
    meta: { title: "Tambah transaksi" },
  },
  {
    path: "/transaksi/:id",
    name: "klasifikasi",
    component: () => import("@/pages/KlasifikasiPage.vue"),
    meta: { title: "Hasil klasifikasi" },
  },
  {
    path: "/asisten",
    name: "asisten",
    component: () => import("@/pages/AsistenPage.vue"),
    meta: { title: "Asisten" },
  },
  {
    path: "/kuota",
    name: "kuota",
    component: () => import("@/pages/KuotaPage.vue"),
    meta: { title: "Kuota dan langganan" },
  },
  {
    path: "/langganan/kembali",
    name: "langganan-kembali",
    component: () => import("@/pages/KuotaPage.vue"),
    meta: { title: "Kuota dan langganan" },
  },
  {
    path: "/profil",
    name: "profil",
    component: () => import("@/pages/ProfilPage.vue"),
    meta: { title: "Profil" },
  },
  { path: "/:pathMatch(.*)*", redirect: "/dasbor" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, _from, saved) {
    if (saved) return saved;
    if (to.hash) return { el: to.hash, behavior: "smooth" };
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  if (to.meta.bare) return true;
  const session = useSessionStore();
  await session.muat();
  if (!session.user) {
    return {
      name: "masuk",
      query: session.sesiBerakhir ? { sesi: "berakhir" } : { lanjut: to.fullPath },
    };
  }
  return true;
});

router.afterEach((to) => {
  const t = to.meta.title as string | undefined;
  document.title = t ? `${t} · KlasifiPajak` : "KlasifiPajak — Kertas Kerja Pajak UMKM";
});
