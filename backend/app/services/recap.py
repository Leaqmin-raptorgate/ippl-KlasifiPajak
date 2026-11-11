"""Annual workpaper recap from stored month snapshots (FR-31, FR-32, FR-36).

Figures are copied from ``berlaku`` rows. This module does not calculate tax
and does not write a PDF archive. ``PDF_OUTPUT_ROOT`` exists so callers can
point at a directory; nothing in this module writes under it.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import MonthSnapshot, User
from app.models import Profile as ProfileRow
from app.security import now_utc
from app.services.dashboard import refresh_if_due
from app.services.profile import find_profile
from app.services.snapshot import DISCLAIMER
from app.services.snapshots_store import rebuild
from app.services.transactions import provisional_usaha_total

PDF_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "assets" / "pdf-output"
_FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf"

# FR-33 text. Secondary source only; not a live billing code and not a payment link.
KAP_KJS = "411128-420"
KAP_KJS_STATUS = "secondary_unconfirmed"

OVERWITHHELD_NOTE = (
    "Kelebihan potong belum diperhitungkan; tidak dikreditkan atau dipindahkan antarbulan. "
    "Konsultasikan dengan konsultan pajak berlisensi."
)
_NOT_AN_SPT = "Pernyataan: berkas ini bukan SPT resmi dan bukan produk DJP/Coretax."
_STALE_MESSAGE = "Masih ada cuplikan berstatus usang tanpa baris berlaku, jadi rekap tidak disusun."
_SCHEME_TEXT = {
    "scheme_eligible": "memenuhi syarat fasilitas",
    "scheme_ineligible": "tidak memenuhi syarat fasilitas",
    "unverifiable": "tidak dapat diverifikasi",
}
_TABLE_HEADINGS = (
    "Bulan",
    "a Bruto",
    "b Akumulasi",
    "c Tidak kena",
    "d Kena pajak",
    "e PPh final",
    "f Disetor sendiri",
    "g Dipotong",
    "h Selisih",
)


def annual_recap(db: Session, user: User, tax_year: int, ruleset) -> dict:
    """FR-31 / FR-36: January-December rows and totals from stored snapshots."""
    profile = find_profile(db, user, tax_year)
    if profile is None:
        raise ApiError(
            404,
            "PROFILE_NOT_FOUND",
            "Profil untuk tahun pajak yang dipilih belum dibuat.",
        )
    rows = _load_berlaku(db, profile, ruleset)
    return _assemble(profile, rows, tax_year, ruleset, provisional_usaha_total(db, user, tax_year))


def workpaper_pdf(db: Session, user: User, tax_year: int, ruleset) -> bytes:
    """FR-31 / FR-32 / FR-36: build one workpaper PDF in memory for this request."""
    return render_workpaper_pdf(annual_recap(db, user, tax_year, ruleset))


def render_workpaper_pdf(recap: dict, *, sample: bool = False) -> bytes:
    """FR-32 / FR-36: render a recap dict to PDF bytes. Does not touch the disk."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(8, 10, 8)
    pdf.add_page()
    pdf.add_font("DejaVu", "", str(_FONT_PATH))
    pdf.set_font("DejaVu", size=14)
    _line(pdf, "DOKUMEN KERJA (WORKPAPER)", 8)
    if sample:
        _line(pdf, "SAMPLE / CONTOH. Bukan dokumen nyata dan bukan arsip unduhan.", 8)
    pdf.set_font("DejaVu", size=11)
    pdf.multi_cell(0, 6, DISCLAIMER, new_x="LMARGIN", new_y="NEXT")
    _line(pdf, _NOT_AN_SPT, 6)
    pdf.set_font("DejaVu", size=9)
    _line(pdf, f"Nama: {recap['name']}", 5)
    _line(pdf, f"Tahun pajak: {recap['tax_year']}", 5)
    _line(pdf, f"Tanggal dibuat (UTC): {recap['generated_on_utc']}", 5)
    _line(pdf, f"ruleset_id: {recap['ruleset_id']}", 5)
    _line(pdf, f"effective_date: {recap['effective_date']}", 5)
    scheme = recap["scheme_eligibility_status"]
    gloss = _SCHEME_TEXT.get(scheme, scheme)
    _line(pdf, f"Status pita dan batas (dari cuplikan): {scheme} ({gloss})", 5)
    next_year = "ya" if recap["next_year_ineligible"] else "tidak"
    _line(pdf, f"Tahun berikutnya tidak memenuhi syarat (dari cuplikan): {next_year}", 5)
    pasal_58 = "aktif" if recap["spouse_aggregation_active"] else "tidak aktif"
    _line(pdf, f"Pasal 58: {pasal_58}", 5)
    annotation = recap.get("annotation") or ""
    if annotation:
        _line(pdf, f"Anotasi cuplikan: {annotation}", 5)
    provisional = int(recap.get("provisional_usaha_omzet_idr") or 0)
    if provisional:
        _line(
            pdf,
            "Rp " + _idr(provisional) + " belum terklasifikasi dan tidak dihitung",
            5,
        )
    _line(
        pdf,
        "Angka dalam rupiah. Kolom f dikosongkan karena aplikasi tidak mencatat setoran sendiri.",
        5,
    )
    pdf.set_font("DejaVu", size=8)
    heading = FontFace(family="DejaVu", emphasis="", size_pt=8)
    with pdf.table(
        col_widths=(1.1, 1, 1.15, 1.1, 1.15, 1.05, 1.25, 1, 1),
        headings_style=heading,
        text_align="CENTER",
        line_height=4,
        first_row_as_headings=True,
    ) as table:
        table.row(_TABLE_HEADINGS)
        for month in recap["months"]:
            table.row(
                (
                    str(month["month"]),
                    _idr(month["usaha_omzet_idr"]),
                    _idr(month["accumulated_usaha_omzet_idr"]),
                    _idr(month["porsi_bebas_idr"]),
                    _idr(month["porsi_kena_idr"]),
                    _idr(month["tax_0_5_pct_idr"]),
                    "",
                    _idr(month["withheld_tax_idr"]),
                    _idr(month["sisa_bayar_idr"]),
                )
            )
        table.row(
            (
                "Total",
                _idr(recap["total_usaha_omzet_idr"]),
                _idr(recap["total_usaha_omzet_idr"]),
                _idr(recap["total_porsi_bebas_idr"]),
                _idr(recap["total_porsi_kena_idr"]),
                _idr(recap["total_tax_0_5_pct_idr"]),
                "",
                _idr(recap["total_withheld_tax_idr"]),
                _idr(recap["total_sisa_bayar_idr"]),
            )
        )
    pdf.set_font("DejaVu", size=9)
    _line(
        pdf,
        "Omzet pekerjaan bebas (terpisah, bukan kolom usaha): Rp "
        + _idr(recap["total_pekerjaan_bebas_omzet_idr"]),
        5,
    )
    if recap["total_overwithheld_excess_idr"]:
        _line(
            pdf,
            "Kelebihan potong: Rp "
            + _idr(recap["total_overwithheld_excess_idr"])
            + " (per bulan: "
            + ", ".join(
                f"{m['month']}: Rp {_idr(m['overwithheld_excess_idr'])}"
                for m in recap["months"]
                if m["overwithheld_excess_idr"]
            )
            + "). "
            + OVERWITHHELD_NOTE,
            5,
        )
    _line(pdf, f"KAP/KJS: {recap['kap_kjs']}", 5)
    _line(
        pdf,
        "Status KAP/KJS: "
        + recap["kap_kjs_status"]
        + ". Sumber sekunder, belum dikonfirmasi. Bukan tautan pembayaran pajak.",
        5,
    )
    pdf.set_font("DejaVu", size=11)
    pdf.multi_cell(0, 6, DISCLAIMER, new_x="LMARGIN", new_y="NEXT")
    _line(pdf, _NOT_AN_SPT, 6)
    payload = pdf.output()
    return bytes(payload)


def _load_berlaku(db: Session, profile: ProfileRow, ruleset) -> list[MonthSnapshot]:
    """Return berlaku rows, rebuilding usang months first (FR-31)."""
    refresh_if_due(db, profile, ruleset)
    had_usang = _any_usang(db, profile.id)
    if had_usang:
        rebuild(db, profile, ruleset, only_usang=True)
    rows = list(
        db.scalars(
            select(MonthSnapshot)
            .where(
                MonthSnapshot.profile_id == profile.id,
                MonthSnapshot.status == "berlaku",
            )
            .order_by(MonthSnapshot.month_key, MonthSnapshot.version)
            .execution_options(populate_existing=True)
        ).all()
    )
    if _usang_without_berlaku(db, profile.id, {row.month_key for row in rows}):
        if had_usang:
            db.rollback()
        raise ApiError(409, "STALE_SNAPSHOT", _STALE_MESSAGE)
    if had_usang:
        db.commit()
    return rows


def _assemble(
    profile: ProfileRow,
    rows: list[MonthSnapshot],
    tax_year: int,
    ruleset,
    provisional: int,
) -> dict:
    """Shape one year of stored amounts. Missing months are integer zeros."""
    chosen: dict[int, MonthSnapshot] = {}
    for row in rows:
        month = _month_number(row.month_key, tax_year)
        if month is None:
            continue
        previous = chosen.get(month)
        if previous is None or row.version >= previous.version:
            chosen[month] = row
    latest = rows[-1] if rows else None
    running = 0
    months: list[dict] = []
    totals = {
        "usaha": 0,
        "bebas": 0,
        "kena": 0,
        "tax": 0,
        "withheld": 0,
        "sisa": 0,
        "pekerjaan": 0,
        "excess": 0,
    }
    for month in range(1, 13):
        row = chosen.get(month)
        usaha = int(row.usaha_omzet_idr) if row else 0
        bebas = int(row.porsi_bebas_idr) if row else 0
        kena = int(row.porsi_kena_idr) if row else 0
        tax = int(row.tax_0_5_pct_idr) if row else 0
        withheld = int(row.withheld_tax_idr) if row else 0
        sisa = int(row.sisa_bayar_idr) if row else 0
        pekerjaan = int(row.pekerjaan_bebas_omzet_idr) if row else 0
        excess = int(row.overwithheld_excess_idr) if row else 0
        running += usaha
        totals["usaha"] += usaha
        totals["bebas"] += bebas
        totals["kena"] += kena
        totals["tax"] += tax
        totals["withheld"] += withheld
        totals["sisa"] += sisa
        totals["pekerjaan"] += pekerjaan
        totals["excess"] += excess
        months.append(
            {
                "month": month,
                "usaha_omzet_idr": usaha,
                "accumulated_usaha_omzet_idr": running,
                "porsi_bebas_idr": bebas,
                "porsi_kena_idr": kena,
                "tax_0_5_pct_idr": tax,
                "self_paid_idr": None,
                "withheld_tax_idr": withheld,
                "sisa_bayar_idr": sisa,
                "overwithheld_excess_idr": excess,
            }
        )
    if latest is None:
        ruleset_id = ruleset.ruleset_id
        effective_date = ruleset.effective_date
        scheme = "scheme_eligible"
        next_year = False
        annotation = ""
    else:
        ruleset_id = latest.ruleset_id
        effective_date = latest.effective_date.isoformat()
        scheme = latest.scheme_eligibility_status
        next_year = bool(latest.next_year_ineligible)
        annotation = latest.annotation or ""
    return {
        "tax_year": tax_year,
        "name": profile.name,
        "generated_on_utc": now_utc().date().isoformat(),
        "ruleset_id": ruleset_id,
        "effective_date": effective_date,
        "disclaimer": DISCLAIMER,
        "kap_kjs": KAP_KJS,
        "kap_kjs_status": KAP_KJS_STATUS,
        "scheme_eligibility_status": scheme,
        "next_year_ineligible": next_year,
        "annotation": annotation,
        "spouse_aggregation_active": bool(profile.spouse_aggregation_active),
        "provisional_usaha_omzet_idr": int(provisional),
        "months": months,
        "total_usaha_omzet_idr": totals["usaha"],
        "total_porsi_bebas_idr": totals["bebas"],
        "total_porsi_kena_idr": totals["kena"],
        "total_tax_0_5_pct_idr": totals["tax"],
        "total_withheld_tax_idr": totals["withheld"],
        "total_sisa_bayar_idr": totals["sisa"],
        "total_overwithheld_excess_idr": totals["excess"],
        "overwithheld_note": OVERWITHHELD_NOTE,
        "total_pekerjaan_bebas_omzet_idr": totals["pekerjaan"],
    }


def _any_usang(db: Session, profile_id: str) -> bool:
    found = db.scalar(
        select(MonthSnapshot.id).where(
            MonthSnapshot.profile_id == profile_id,
            MonthSnapshot.status == "usang",
        )
    )
    return found is not None


def _usang_without_berlaku(db: Session, profile_id: str, berlaku_keys: set[str]) -> bool:
    stale_keys = db.scalars(
        select(MonthSnapshot.month_key).where(
            MonthSnapshot.profile_id == profile_id,
            MonthSnapshot.status == "usang",
        )
    ).all()
    return any(key not in berlaku_keys for key in stale_keys)


def _month_number(month_key: str, tax_year: int) -> int | None:
    year_text, _, month_text = month_key.partition("-")
    if year_text != str(tax_year) or len(month_text) != 2 or not month_text.isdigit():
        return None
    month = int(month_text)
    if month < 1 or month > 12:
        return None
    return month


def _idr(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".")


def _line(pdf: FPDF, text: str, height: float) -> None:
    pdf.cell(0, height, text, new_x="LMARGIN", new_y="NEXT")
