import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { bindSessionLoss } from "./lib/api";
import { router } from "./router";
import { useSessionStore, watchSystemTheme } from "./stores/session";
import "./styles/base.css";
import "./styles/motion.css";

watchSystemTheme();

const pinia = createPinia();
bindSessionLoss((code) => {
  const session = useSessionStore(pinia);
  session.jatuh(code);
  if (router.currentRoute.value.meta.bare !== true) {
    void router.push({
      name: "masuk",
      query: session.sesiBerakhir ? { sesi: "berakhir" } : {},
    });
  }
});

const app = createApp(App).use(pinia).use(router);
router.isReady().then(() => app.mount("#app"));
