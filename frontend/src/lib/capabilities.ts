/**
 * Which user-facing features the backend can actually serve.
 *
 * A flag is `true` only when the route behind that feature is implemented. A
 * page reads it with `v-if`, so a feature that is off is not rendered at all:
 * never a disabled control with a tooltip, because a control that can never
 * succeed is worse than no control.
 *
 * Flipping one boolean is the only edit needed when its route lands. The store
 * methods and the wire types stay in place either way; they are simply not
 * called from a rendered control while the flag is `false`.
 */
export const CAPABILITIES = Object.freeze({
  /** `POST /recap/{tax_year}/pdf`. The "Unduh workpaper" button. */
  workpaperExport: true,
  /** `POST /transactions/reclassify`. Re-classify a list of rows on the ledger. */
  reclassifyAll: true,
  /** `POST /assistant/query`. The ask form, its quota chip, and its suggestions. */
  assistantChat: true,
  /** `POST /transactions/ocr-upload`, then `POST /transactions/ocr-confirm`. */
  ocrUpload: true,
  /** `POST /auth/password-reset/request`, then `POST /auth/password-reset/confirm`. */
  passwordReset: true,
  /** `GET /auth/sessions`, and the revoke calls on the same path. */
  activeSessions: true,
  /** `POST /transactions/{id}/override`. */
  manualOverride: true,
  /** `DELETE /transactions/{id}`. Deleting one row and rebuilding its month. */
  deleteTransaction: true,
  /** `GET` and `POST /subscriptions/orders`. */
  subscriptionPurchase: false,
  /** `GET /transactions/{id}/audit-trail`. */
  auditTrail: true,
} as const);

/** One feature name, for a caller that takes a name rather than one flag. */
export type Capability = keyof typeof CAPABILITIES;
