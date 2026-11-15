/** Quotas and the paid plan. A missing route stays empty; it is not a free tier. */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import type { Quotas, SubscriptionOrder, SubscriptionStatus } from "@/lib/wire";

export const useKuotaStore = defineStore("kuota", () => {
  const quotas = ref<Quotas | null>(null);
  const status = ref<SubscriptionStatus | null>(null);
  const orders = ref<SubscriptionOrder[]>([]);
  const pesan = ref("");
  const bayarPesan = ref("");
  const memproses = ref(false);

  const berbayar = computed(
    () => status.value?.paid_flag === true && status.value.subscription_tier === "berbayar",
  );
  const labelTier = computed(() => {
    const tier = status.value?.subscription_tier;
    if (tier === "berbayar") return "Berbayar";
    if (tier === "pending") return "Menunggu bayar";
    if (tier === "kedaluwarsa") return "Kedaluwarsa";
    if (tier === "gratis") return "Gratis";
    return "";
  });

  /** A 404 means "not created yet" for a brand-new account: an empty state, not an error. */
  function belumAda(error: unknown): boolean {
    return error instanceof ApiFailure && error.status === 404;
  }

  let muatBerjalan: Promise<void> | null = null;

  /**
   * The one owner of the Kuota read. A plain call joins a read already in flight,
   * so the shell and the page that mount together send one request per resource.
   * `paksa` starts a fresh read for the re-reads that must see new data (polling,
   * a return from the back/forward cache, a refresh after an order).
   */
  function muat(paksa = false): Promise<void> {
    if (muatBerjalan && !paksa) return muatBerjalan;
    const selesai: Promise<void> = bacaUlang().finally(() => {
      if (muatBerjalan === selesai) muatBerjalan = null;
    });
    muatBerjalan = selesai;
    return selesai;
  }

  async function bacaUlang() {
    pesan.value = "";
    try {
      quotas.value = await api<Quotas>("/quotas");
    } catch (error) {
      quotas.value = null;
      if (!belumAda(error)) {
        pesan.value = error instanceof ApiFailure ? error.message : "Kuota belum tersedia.";
      }
    }
    try {
      status.value = await api<SubscriptionStatus>("/subscriptions/status");
    } catch (error) {
      status.value = null;
      if (!pesan.value && error instanceof ApiFailure && !belumAda(error)) {
        pesan.value = error.message;
      }
    }
    // Only ask for order history when the route exists. A call that can only
    // 404 is noise in the network tab and a lie in the console.
    if (CAPABILITIES.subscriptionPurchase) {
      try {
        const data = await api<{ items?: SubscriptionOrder[] } | SubscriptionOrder[]>(
          "/subscriptions/orders",
        );
        orders.value = Array.isArray(data) ? data : (data.items ?? []);
      } catch {
        orders.value = [];
      }
    } else {
      orders.value = [];
    }
  }

  /** One order request at a time: an overlapping call joins the one in flight. */
  let berjalan: Promise<SubscriptionOrder> | null = null;
  let dialihkan = false;

  function buatPesanan(planId = "monthly_25k"): Promise<SubscriptionOrder> {
    if (berjalan) return berjalan;
    memproses.value = true;
    dialihkan = false;
    bayarPesan.value = "";
    berjalan = kirimPesanan(planId).then(
      (order) => {
        // After a redirect the page is leaving: keep the guard (and the
        // in-flight promise) so a second click cannot create another order.
        if (!dialihkan) {
          berjalan = null;
          memproses.value = false;
        }
        return order;
      },
      (error) => {
        berjalan = null;
        memproses.value = false;
        throw error;
      },
    );
    return berjalan;
  }

  /** Release the order guard, for a page restored from the back/forward cache after the redirect. */
  function lepasPesanan() {
    berjalan = null;
    dialihkan = false;
    memproses.value = false;
  }

  async function kirimPesanan(planId: string): Promise<SubscriptionOrder> {
    const order = await api<SubscriptionOrder>("/subscriptions/orders", {
      method: "POST",
      body: JSON.stringify({ plan_id: planId }),
    });
    if (order.status === "pending" && order.payment_url) {
      dialihkan = true;
      window.location.assign(order.payment_url);
    } else {
      bayarPesan.value =
        order.status === "pending"
          ? "Tautan bayar belum siap. Coba lagi sebentar."
          : "Pesanan ini sudah tidak menunggu pembayaran, jadi tautan bayar tidak tersedia. Status akun dan riwayat pesanan dibaca ulang.";
      await muat(true);
    }
    return order;
  }

  return {
    quotas,
    status,
    orders,
    pesan,
    bayarPesan,
    memproses,
    berbayar,
    labelTier,
    muat,
    buatPesanan,
    lepasPesanan,
  };
});
