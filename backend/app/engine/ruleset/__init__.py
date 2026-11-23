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
cannot answer both. The four stored categories stay as they are.

The owner decided on 2026-11-23 that ordinary bank-deposit interest, savings
interest, personal investment dividends and personal lottery winnings are
outside both the 0.5% base and the Rp4.8bn test. This is an academic project
decision, not a tax-adviser sign-off. The source of the income is the decisive
point. Pasal 58 ayat (1) huruf a counts turnover from business and independent
professional services. DJP FAQ 31, pp. 32-33, is the cited basis for excluding
dividends received as a shareholder. Deposit interest and lottery prizes are
the owner's application of that same source rule.

Today's matrix, pinned by test:

- Goods or services sale: in the 0.5% base, in the Rp4.8bn test, ``usaha``.
- Freelance service on the Pasal 56(4) list: not in the 0.5% base, in the
  test, ``pekerjaan_bebas``.
- Rent of land or a building: not in the 0.5% base, in the test,
  ``already_final``.
- Business income earned abroad and taxed abroad: not in the 0.5% base, in
  the test. The user enters it as another category. There is no extra rule.
- Deposit or savings interest: not in the 0.5% base, not in the test.
  Phrases ``bunga deposito``, ``bunga bank`` and ``bunga tabungan`` store
  ``non_object`` (``non_object.deposit``, ``non_object.bank``,
  ``non_object.savings``). A description that is only ``bunga`` stays
  clarification, because interest from a lending business can count.
- Dividend: phrase ``dividen``, id ``non_object.dividend``. Same exclusion.
- Lottery prize: the rule phrase is ``hadiah undian`` only, id
  ``non_object.prize``. Do not widen the phrase to ``hadiah``.
- Other prizes (a competition or an award): not decided. The lottery rule
  does not match, so the row stays clarification.
- Gift, inheritance, loan received, or a transfer between the user's own
  accounts: not in the 0.5% base, not in the test, ``non_object``.

Wording for interest, dividends and lottery prizes: dikenai PPh final
tersendiri. The ``non_object`` label describes the computation. It does not
say the money is untaxed. Deposit interest and lottery prizes keep their own
PPh rules, and dividends can have separate treatment.
"""

from app.engine.ruleset.load import load_ruleset

__all__ = ["load_ruleset"]
