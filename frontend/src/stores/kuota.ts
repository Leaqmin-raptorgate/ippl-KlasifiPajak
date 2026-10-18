/** Quotas and the paid plan. A missing route stays empty; it is not a free tier. */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import type { Quotas, SubscriptionOrder, SubscriptionStatus } from "@/lib/wire";

export const useKuotaStore = defineStore("kuota", () => {
  const quotas = ref<Quotas | null>(null);
  const status = ref<SubscriptionStatus | null>(null);
  const orders = ref<SubscriptionOrder[]>([]);
  const pesan = ref("");
  const bayarPesan = ref("");

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

  async function muat() {
    pesan.value = "";
    try {
      quotas.value = await api<Quotas>("/quotas");
    } catch (error) {
      quotas.value = null;
      pesan.value = error instanceof ApiFailure ? error.message : "Kuota belum tersedia.";
    }
    try {
      status.value = await api<SubscriptionStatus>("/subscriptions/status");
    } catch (error) {
      status.value = null;
      if (!pesan.value && error instanceof ApiFailure) pesan.value = error.message;
    }
    try {
      const data = await api<{ items?: SubscriptionOrder[] } | SubscriptionOrder[]>(
        "/subscriptions/orders",
      );
      orders.value = Array.isArray(data) ? data : (data.items ?? []);
    } catch {
      orders.value = [];
    }
  }

  async function buatPesanan(planId = "monthly_25k") {
    bayarPesan.value = "";
    const order = await api<SubscriptionOrder>("/subscriptions/orders", {
      method: "POST",
      body: JSON.stringify({ plan_id: planId }),
    });
    if (order.payment_url) window.location.assign(order.payment_url);
    else bayarPesan.value = "Pesanan tercatat, tetapi tautan bayar tidak ada pada jawaban.";
    return order;
  }

  return { quotas, status, orders, pesan, bayarPesan, berbayar, labelTier, muat, buatPesanan };
});
