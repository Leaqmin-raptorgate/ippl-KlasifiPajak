"""Ruleset files. Numbers live here, not in the engine.

This package ships tax year 2026 only (`pp20-2026-academic-1`). A different
tax year needs its own ruleset rule. Spouse turnover for 2026 follows
PP 20/2026 Pasal 58 ayat (2) and ayat (3). The Penjelasan to ayat (2)
includes a minor child's turnover in the husband-and-wife combination.
Ayat (3) also includes a single-person company founded by the couple.
Neither amount is an engine input. `spouse_in_cap` and `spouse_in_band`
stay ruleset data, and the Rp500m band is unchanged.

`spouse_tax_status` maps to `spouse_aggregation_active` for 2026 as follows.
`unmarried` is false (no spouse). `separate` (PH or MT) is true under
Pasal 58(2). `joint` is false as a product assumption: the couple uses one
account, so the spouse's turnover is already in it. `unknown` is false, the
result may be inexact, and that choice is not signed off. When a profile
save includes `spouse_tax_status`, the stored flag is true only for
`separate`. Omitting the status stores the flag that was sent.

Income has two separate questions: whether it is inside the 0.5% base, and
whether it counts in the Rp4.8bn gross-turnover test. One stored category
cannot answer both. The four stored categories stay as they are. Ids are
not renamed. Deposit interest, dividends and lottery prizes are final-taxed
and are stored as ``non_object`` under ``already_final.deposit``,
``already_final.bank``, ``already_final.dividend`` and ``already_final.prize``.
That storage does not mean they sit outside the tax object.

Today's matrix, pinned by test, with no change to classification or the cap:

- Goods or services sale: in the 0.5% base, in the Rp4.8bn test, ``usaha``.
- Freelance service on the Pasal 56(4) list: not in the 0.5% base, in the
  test, ``pekerjaan_bebas``.
- Rent of land or a building: not in the 0.5% base, in the test,
  ``already_final``.
- Business income earned abroad and taxed abroad: not in the 0.5% base, in
  the test. The user enters it as another category. There is no extra rule.
- Deposit or savings interest: not in the 0.5% base. Not in the Rp4.8bn
  test is an inference from Pasal 58(1)(a), not signed off. Stored as
  ``non_object`` (``already_final.deposit``, ``already_final.bank``).
- Dividend to a resident individual: same, id ``already_final.dividend``.
- Lottery prize: the rule phrase is ``hadiah undian`` only. Same inference.
  Stored as ``non_object``, id ``already_final.prize``. Do not widen the
  phrase to ``hadiah``.
- Other prizes (a competition or an award): not decided. The lottery rule
  does not match, so the row stays clarification.
- Gift, inheritance, loan received, or a transfer between the user's own
  accounts: not in the 0.5% base, not in the test, ``non_object``.

Wording for interest, dividends and lottery prizes: dikenai PPh final
tersendiri; tidak dihitung dalam peredaran bruto usaha. Do not call those
rows outside the tax object. The guidance item ``separate_final_income``
uses that sentence for what the app records today.
"""

from app.engine.ruleset.load import load_ruleset

__all__ = ["load_ruleset"]
