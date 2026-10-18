/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the API, without the `/api/v1` suffix. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, unknown>;
  export default component;
}
