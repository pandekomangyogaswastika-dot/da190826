#!/usr/bin/env python3
"""verify_fase_g2_penomoran_ditegakkan.py — FASE G lanjutan (2026-08-17, sesi #18).

GATE **INV-F25** — "SETELAN PENOMORAN TIDAK BOLEH BERBOHONG."

YANG TERUKUR SEBELUM PERBAIKAN:
  · Layar Administrasi Sistem → Penomoran Dokumen menampilkan pilihan
    **Otomatis / Manual** untuk **49 jenis dokumen**, tetapi hanya **2** jalur tulis
    (PO Produksi & Roll Kain) yang benar-benar memanggil
    `core.doc_number_policy.issue_number`. Untuk 47 jenis lainnya owner bisa memindah
    ke "Manual", setelan itu TERSIMPAN, layar menampilkannya — dan dokumennya tetap
    bernomor otomatis. Setelan yang tidak ditegakkan lebih buruk daripada setelan yang
    tidak ada: ia membuat orang percaya sudah mengubah sesuatu.
  · Kasbon & Pinjaman memakai SATU field (`dewi_kasbon_requests.request_number`) dengan
    awalan berbeda (KSB/PIN), tetapi registry hanya punya satu kunci ⇒ satu kebijakan
    dipaksa untuk dua jenis dokumen.
  · Nomor kasbon yang lahir (`KSB-00001`) tidak mengikuti format yang tertulis di layar
    (`KSB-{YYYY}{MM}-{SEQ:5}`) — layar dan kenyataan berbeda.

INVARIAN:
  G1  setiap jenis dokumen ber-`policy_enforced` BENAR-BENAR lewat `issue_number`
      (statik: jalur tulisnya diperiksa, bukan dipercaya)
  G2  mode MANUAL: nomor kosong DITOLAK, pola bebas DITOLAK, pola benar DITERIMA
  G3  mode OTOMATIS: nomor ketikan DITOLAK (bukan diabaikan) & nomor yang lahir
      mengikuti FORMAT yang disetel owner
  G4  jenis dokumen yang BELUM ditegakkan: perubahan mode DITOLAK API (setelan tidak
      berbohong), sementara perubahan FORMAT tetap boleh
  G5  Kasbon & Pinjaman punya kebijakan TERPISAH (memindah satu tidak menyeret yang lain)
  G6  nomor unik: nomor manual yang sudah dipakai DITOLAK (409)
  G7  LAYAR memakai kebijakan: form kasbon membaca `/doc-number-policy` dan layar admin
      menyembunyikan pilihan mode untuk jenis yang belum ditegakkan
  G9  (SESI #19) setiap jenis dokumen berlabel jelas: ditegakkan · selalu otomatis
      (dengan ALASAN yang tampil di layar) · menunggu — tidak ada yang menggantung
  G8  (SESI #19) tiga jenis tambahan — **Surat Jalan Gudang**, **PR Pengadaan**,
      **Jurnal Umum** — ditegakkan pada DOKUMEN SUNGGUHAN: mode otomatis menolak
      nomor ketikan & nomor lahir mengikuti format owner; mode manual menolak nomor
      kosong, nomor berpola bebas, dan nomor kembar (409)

Self-cleaning: seluruh pengajuan uji (`UJI-G2 …`) dan setelan mode dikembalikan.

Pakai:  python3 scripts/verify_fase_g2_penomoran_ditegakkan.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

MARK = f"UJI-G2 {time.strftime('%H%M%S')}"
KASBON_KEY = "dewi_kasbon_requests.request_number"
PINJAMAN_KEY = "dewi_kasbon_requests.request_number_pinjaman"
# SESI #19 — kunci "belum ditegakkan" untuk menguji G4. DULU memakai
# `rahaza_journal_entries.je_number`; jurnal kini DITEGAKKAN, jadi kunci itu tidak
# lagi bisa membuktikan penolakan mode. Dipilih Nota Kredit (masih otomatis penuh).
# Format yang dikirim pada uji G4 sengaja SAMA dengan bawaan registry supaya
# menjalankan gate tidak mengubah perilaku penomoran apa pun.
NOT_ENFORCED_KEY = "rahaza_orders.order_number"          # ada formnya, MENUNGGU disambungkan
NOT_ENFORCED_FORMAT = "ORD-{YYYY}{MM}{DD}-{SEQ:3}"
AUTO_ONLY_KEY = "rahaza_credit_notes.cn_number"          # lahir tanpa manusia

# Jalur tulis yang WAJIB memanggil issue_number untuk tiap kunci ber-policy_enforced.
WRITE_PATHS = {
    "production_pos.po_number": "backend/routes/production_pos.py",
    "production_pos.po_number_maklon": "backend/routes/production_pos.py",
    "wh_fabric_rolls.roll_no": "backend/core/fabric_roll_engine.py",
    "cmt_receipts.receipt_code": "backend/routes/dewi_cmt_packing.py",
    "dewi_maklon_invoices.invoice_number": "backend/routes/dewi_maklon_billing.py",
    "rahaza_ar_invoices.invoice_number": "backend/routes/rahaza_finance.py",
    KASBON_KEY: "backend/routes/dewi_kasbon.py",
    PINJAMAN_KEY: "backend/routes/dewi_kasbon.py",
    # SESI #19 — tiga jenis tambahan (permintaan owner)
    "wh_delivery_notes.sj_number": "backend/routes/wms_delivery_notes.py",
    "dewi_procurement_requests.request_number": "backend/routes/dewi_procurement.py",
    "rahaza_journal_entries.je_number": "backend/routes/rahaza_journals.py",
    # SESI #19 batch-2 (penomoran menyeluruh): dokumen UANG & STOK yang dibuat orang
    "rahaza_purchase_orders.po_number": "backend/routes/rahaza_po.py",
    "rahaza_material_issues.mi_number": "backend/routes/rahaza_inventory_shared.py",
    "wh_returns.return_code": "backend/routes/dewi_wh_returns.py",
}

# SESI #19 — FORM yang wajib membaca kebijakan (bukan sekadar backend yang menegakkan):
# form tanpa kolom nomor membuat mode MANUAL berarti "dokumen tidak bisa dibuat".
FORM_PATHS = {
    "wh_delivery_notes.sj_number":
        "frontend/src/components/erp/WMSDeliveryNotesModule.jsx",
    "dewi_procurement_requests.request_number":
        "frontend/src/components/erp/ProcurementRequestModule.jsx",
    "rahaza_journal_entries.je_number":
        "frontend/src/components/erp/RahazaJournalEntryModule.jsx",
    KASBON_KEY: "frontend/src/components/erp/KasbonStaffModule.jsx",
    "rahaza_purchase_orders.po_number":
        "frontend/src/components/erp/PurchaseOrderModule.jsx",
    "rahaza_material_issues.mi_number":
        "frontend/src/components/erp/RahazaMaterialIssueModule.jsx",
    "wh_returns.return_code":
        "frontend/src/components/erp/WHReturnsModule.jsx",
}

PASS, FAIL = [], []


def ok(code, msg, extra=""):
    PASS.append(code)
    print(f"{G}  ✓ {code}{X} {msg}" + (f"\n         {C}{extra}{X}" if extra else ""))


def bad(code, msg, extra=""):
    FAIL.append(code)
    print(f"{R}  ✗ {code}{X} {msg}" + (f"\n         {extra}" if extra else ""))


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        d = e.read()
        return e.code, (json.loads(d or b"{}") if d[:1] in (b"{", b"[")
                        else {"raw": d[:300].decode(errors="ignore")})
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def det(d) -> str:
    return str((d or {}).get("detail") or (d or {}).get("raw") or d)[:400]


def set_mode(token, key, mode):
    return call("PUT", "/api/admin/doc-numbering", token,
                {"key": key, "mode": mode, "active": True})[0]


def ajukan(token, jenis, nomor=None, cicilan=1):
    body = {"type": jenis, "amount": 250000, "purpose": MARK,
            "reason": MARK, "installment_count": cicilan}
    if nomor is not None:
        body["request_number"] = nomor
    st, d = call("POST", "/api/dewi/kasbon/requests", token, body)
    return st, d, ((d or {}).get("request") or {}).get("request_number")


# ═════════════ SESI #19 — tiga jenis dokumen baru (SJ Gudang · PR · Jurnal) ════
# Dibuktikan pada DOKUMEN SUNGGUHAN lewat API, bukan dengan membaca kode: satu
# jenis bisa "memanggil issue_number" tetapi tetap salah bila formnya mengirim
# nomor pada mode otomatis atau modelnya membuang kolom nomor.
YMD = time.strftime("%Y%m%d")
SJ_TIPE = "SJ-INTERNAL"


def buat_sj(token, nomor=None):
    body = {"sj_type": SJ_TIPE, "recipient_name": MARK, "recipient_address": MARK,
            "notes": MARK, "lines": [{"description": MARK, "qty": 1, "unit": "pcs"}]}
    if nomor is not None:
        body["sj_number"] = nomor
    st, d = call("POST", "/api/wms/delivery-notes", token, body)
    return st, d, ((d or {}).get("sj") or {}).get("sj_number")


def buat_pr(token, nomor=None):
    body = {"title": MARK, "justification": MARK, "department": MARK,
            "items": [{"name": MARK, "qty": 1, "uom": "pcs", "estimated_price": 1000}]}
    if nomor is not None:
        body["request_number"] = nomor
    st, d = call("POST", "/api/procurement/requests", token, body)
    return st, d, (d or {}).get("request_number")


def buat_je(token, akun, nomor=None):
    body = {"date": time.strftime("%Y-%m-%d"), "memo": MARK, "post": False,
            "lines": [{"account_code": akun[0], "debit": 1000, "credit": 0,
                       "description": MARK},
                      {"account_code": akun[1], "debit": 0, "credit": 1000,
                       "description": MARK}]}
    if nomor is not None:
        body["je_number"] = nomor
    st, d = call("POST", "/api/rahaza/journals", token, body)
    return st, d, (d or {}).get("je_number")


def akun_jurnal(token) -> list:
    """Dua akun leaf yang sah untuk jurnal uji (tanpa mengubah data master)."""
    _st, d = call("GET", "/api/rahaza/coa/accounts", token)
    rows = d if isinstance(d, list) else (d or {}).get("items") or []
    leaf = [r.get("code") for r in rows
            if not r.get("is_group") and r.get("active") is not False and r.get("code")]
    return leaf[:2]


# ═════════════════════ G1 & G7 — statik ═══════════════════════════════════════

def part_static():
    print(f"\n{B}[1] STATIK — yang ditandai 'ditegakkan' benar-benar menegakkan{X}")
    from data.doc_number_registry import DOC_NUMBER_REGISTRY
    enforced = [e["key"] for e in DOC_NUMBER_REGISTRY if e.get("policy_enforced")]
    missing = []
    for key in enforced:
        rel = WRITE_PATHS.get(key)
        if not rel:
            missing.append(f"{key} (jalur tulisnya tidak terdaftar di gate ini)")
            continue
        src = (ROOT / rel).read_text(encoding="utf-8")
        if "issue_number" not in src:
            missing.append(f"{key} → {rel} tidak memanggil issue_number")
    if enforced and not missing:
        ok("G1", f"{len(enforced)} jenis dokumen ber-'policy_enforced' benar-benar lewat "
                 "satu pintu issue_number", ", ".join(k.split(".")[-1] for k in enforced))
    else:
        bad("G1", "ada jenis dokumen yang MENGAKU ditegakkan tetapi jalur tulisnya tidak",
            "; ".join(missing) or "tidak ada jenis yang ditandai")

    # ── G9 (SESI #19): TIDAK ADA JENIS YANG STATUSNYA MENGGANTUNG ──────────────
    # Sebelum ini, 38 dari 49 jenis dokumen hanya "belum ditegakkan" tanpa keterangan:
    # pemilik tidak bisa membedakan "nanti bisa diatur" dari "memang mustahil diatur
    # karena dokumennya lahir tanpa manusia". Setiap entri sekarang WAJIB berlabel
    # tepat satu: `policy_enforced` · `auto_only` (+alasan) · `pending_enforce`.
    tanpa_label, tanpa_alasan, ganda = [], [], []
    for e in DOC_NUMBER_REGISTRY:
        label = [k for k in ("policy_enforced", "auto_only", "pending_enforce") if e.get(k)]
        if not label:
            tanpa_label.append(e["key"])
        elif len(label) > 1:
            ganda.append(f"{e['key']} ({'+'.join(label)})")
        if e.get("auto_only") and not str(e.get("alasan_otomatis") or "").strip():
            tanpa_alasan.append(e["key"])
    admin_src = (ROOT / "frontend/src/components/erp/DocNumberingModule.jsx").read_text(encoding="utf-8")
    m9 = []
    if tanpa_label:
        m9.append(f"jenis tanpa keterangan status: {tanpa_label[:6]}")
    if ganda:
        m9.append(f"jenis berlabel ganda: {ganda[:4]}")
    if tanpa_alasan:
        m9.append(f"'selalu otomatis' tanpa alasan: {tanpa_alasan[:6]}")
    if "auto_only" not in admin_src or "alasan_otomatis" not in admin_src:
        m9.append("layar admin tidak menampilkan ALASAN jenis yang selalu otomatis")
    if not m9:
        _en = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("policy_enforced"))
        _ao = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("auto_only"))
        _pe = sum(1 for e in DOC_NUMBER_REGISTRY if e.get("pending_enforce"))
        ok("G9", f"{len(DOC_NUMBER_REGISTRY)} jenis dokumen semuanya terklasifikasi & "
                 "layar menyebut alasannya",
           f"ditegakkan {_en} · selalu otomatis {_ao} (berlasan) · menunggu {_pe}")
    else:
        bad("G9", "status penomoran sebagian jenis masih menggantung", "; ".join(m9))

    form = (ROOT / "frontend/src/components/erp/KasbonStaffModule.jsx").read_text(encoding="utf-8")
    admin = (ROOT / "frontend/src/components/erp/DocNumberingModule.jsx").read_text(encoding="utf-8")
    shared = ROOT / "frontend/src/components/erp/docnum/DocNumberField.jsx"
    miss7 = []
    if not shared.exists():
        miss7.append("komponen bersama docnum/DocNumberField.jsx tidak ada")
    for probe in ("useDocNumberPolicy", PINJAMAN_KEY, "docNumberPayload"):
        if probe not in form:
            miss7.append(f"form kasbon tidak memakai {probe}")
    if "policy_enforced" not in admin or "docnum-mode-locked-" not in admin:
        miss7.append("layar admin tidak menyembunyikan pilihan mode untuk jenis "
                     "yang belum ditegakkan")
    # SESI #19 — setiap jenis yang ditegakkan HARUS punya kolom nomor di formnya.
    for key, rel in FORM_PATHS.items():
        p = ROOT / rel
        if not p.exists():
            miss7.append(f"{key}: form {rel} tidak ada")
            continue
        src = p.read_text(encoding="utf-8")
        if "DocNumberField" not in src or "useDocNumberPolicy" not in src:
            miss7.append(f"{key}: {rel} belum memasang <DocNumberField>")
        elif key not in src:
            miss7.append(f"{key}: {rel} memasang DocNumberField tetapi bukan untuk kunci ini")
    if not miss7:
        ok("G7", "LAYAR memakai kebijakan: form kasbon membaca kebijakan & layar admin jujur",
           f"DocNumberField dipakai {len(FORM_PATHS)} form (kasbon · surat jalan gudang · PR · "
           "jurnal umum); toggle mode hanya untuk yang ditegakkan")
    else:
        bad("G7", "layar belum memakai kebijakan", "; ".join(miss7))


# ═════════════════════ G2..G6 — runtime ══════════════════════════════════════

def part_runtime(token, db):
    print(f"\n{B}[2] RUNTIME — mode ditegakkan pada dokumen sungguhan{X}")

    # ── G3: OTOMATIS ──
    set_mode(token, KASBON_KEY, "auto")
    st_typed, d_typed, _ = ajukan(token, "kasbon", nomor="BEBAS-999")
    st_auto, _d, no_auto = ajukan(token, "kasbon")
    _stp, pol = call("GET", f"/api/doc-number-policy?key={KASBON_KEY}", token)
    fmt_ok = bool(no_auto) and bool(re.match((pol or {}).get("pola") or "^$", no_auto or ""))
    if (st_typed == 400 and "tidak boleh diketik" in det(d_typed).lower()
            and st_auto == 200 and fmt_ok):
        ok("G3", "mode OTOMATIS menolak nomor ketikan & nomor yang lahir mengikuti FORMAT owner",
           f"ketikan HTTP {st_typed} · otomatis → {no_auto} (pola {(pol or {}).get('format')})")
    else:
        bad("G3", "mode otomatis tidak ditegakkan / nomor tidak mengikuti format",
            f"ketikan HTTP {st_typed} {det(d_typed)[:90]} · auto HTTP {st_auto} nomor={no_auto} "
            f"pola={(pol or {}).get('pola')}")

    # ── G2: MANUAL ──
    set_mode(token, KASBON_KEY, "manual")
    st_empty, d_empty, _ = ajukan(token, "kasbon")
    st_free, d_free, _ = ajukan(token, "kasbon", nomor="KASBON/BEBAS/9")
    good = f"KSB-{time.strftime('%Y%m')}-99001"
    st_good, _dg, no_good = ajukan(token, "kasbon", nomor=good)
    if (st_empty == 400 and "wajib diisi" in det(d_empty).lower()
            and st_free == 400 and "tidak mengikuti pola" in det(d_free).lower()
            and st_good == 200 and no_good == good):
        ok("G2", "mode MANUAL: kosong ditolak · pola bebas ditolak · pola benar diterima",
           f"kosong {st_empty} · bebas {st_free} · benar {st_good} → {no_good}")
    else:
        bad("G2", "mode manual tidak ditegakkan sebagaimana mestinya",
            f"kosong={st_empty} bebas={st_free} benar={st_good} nomor={no_good}")

    # ── G6: nomor kembar ──
    st_dup, d_dup, _ = ajukan(token, "kasbon", nomor=good)
    if st_dup == 409 and "sudah dipakai" in det(d_dup).lower():
        ok("G6", "nomor manual yang sudah dipakai DITOLAK (409) — nomor dokumen tetap unik",
           f"'{good}' → HTTP {st_dup}")
    else:
        bad("G6", "nomor manual kembar diterima ⇒ dua dokumen bernomor sama",
            f"HTTP {st_dup} {det(d_dup)[:120]}")

    # ── G5: Kasbon manual TIDAK menyeret Pinjaman ──
    st_pin, _dp, no_pin = ajukan(token, "pinjaman", cicilan=4)
    _stpp, polp = call("GET", f"/api/doc-number-policy?key={PINJAMAN_KEY}", token)
    if (st_pin == 200 and no_pin and no_pin.startswith("PIN-")
            and (polp or {}).get("mode") == "auto"):
        ok("G5", "Kasbon MANUAL tidak menyeret Pinjaman — dua jenis dokumen, dua kebijakan",
           f"pinjaman tetap otomatis → {no_pin}")
    else:
        bad("G5", "kebijakan kasbon & pinjaman masih tercampur",
            f"HTTP {st_pin} nomor={no_pin} mode_pinjaman={(polp or {}).get('mode')}")
    set_mode(token, KASBON_KEY, "auto")

    # ── G4: jenis yang BELUM ditegakkan ──
    st_mode = set_mode(token, NOT_ENFORCED_KEY, "manual")
    st_m, d_m = call("PUT", "/api/admin/doc-numbering", token,
                     {"key": NOT_ENFORCED_KEY, "mode": "manual", "active": True})
    st_fmt, _df = call("PUT", "/api/admin/doc-numbering", token,
                       {"key": NOT_ENFORCED_KEY,
                        "format": NOT_ENFORCED_FORMAT, "active": True})
    cfg = db.doc_number_configs.find_one({"key": NOT_ENFORCED_KEY}, {"_id": 0}) or {}
    # SESI #19 — DUA jenis penolakan diuji terpisah supaya pesannya tidak boleh
    # tertukar: yang MENUNGGU disambungkan vs yang SELALU otomatis (lahir tanpa
    # manusia). Pesan seragam membuat pemilik menunggu sesuatu yang tidak akan datang.
    st_ao, d_ao = call("PUT", "/api/admin/doc-numbering", token,
                       {"key": AUTO_ONLY_KEY, "mode": "manual", "active": True})
    if (st_mode == 400 and st_m == 400 and "belum bisa diubah" in det(d_m).lower()
            and st_fmt == 200 and cfg.get("mode") in (None, "auto")
            and st_ao == 400 and "selalu bernomor otomatis" in det(d_ao).lower()):
        ok("G4", "penolakan mode JUJUR & terpisah: 'menunggu disambungkan' vs 'selalu "
                 "otomatis (beralasan)'; FORMAT tetap boleh diubah",
           f"menunggu HTTP {st_m} · selalu-otomatis HTTP {st_ao} · format HTTP {st_fmt}")
    else:
        bad("G4", "setelan mode diterima / pesannya tidak jujur",
            f"menunggu {st_m} {det(d_m)[:80]} · selalu-otomatis {st_ao} {det(d_ao)[:80]} "
            f"· format {st_fmt} · mode tersimpan={cfg.get('mode')}")


def part_runtime_baru(token, db):
    """SESI #19 — G8: tiga jenis baru ditegakkan pada dokumen SUNGGUHAN."""
    print(f"\n{B}[3] RUNTIME BARU — Surat Jalan Gudang · PR Pengadaan · Jurnal Umum{X}")
    akun = akun_jurnal(token)
    jenis = [
        ("Surat Jalan Gudang", "wh_delivery_notes.sj_number",
         lambda n=None: buat_sj(token, n),
         f"{SJ_TIPE}/{time.strftime('%Y/%m')}/9901", "KIRIM/BEBAS/9"),
        ("PR Pengadaan", "dewi_procurement_requests.request_number",
         lambda n=None: buat_pr(token, n),
         f"PR-{time.strftime('%Y%m')}-9901", "PR/BEBAS/9"),
        ("Jurnal Umum", "rahaza_journal_entries.je_number",
         lambda n=None: buat_je(token, akun, n),
         f"JE-{YMD}-9901", "JURNAL/BEBAS/9"),
    ]
    if len(akun) < 2:
        bad("G8", "tidak menemukan 2 akun leaf untuk jurnal uji — invarian tidak bisa diukur",
            f"akun terbaca: {akun}")
        return

    rusak, bukti = [], []
    for label, key, buat, nomor_benar, nomor_bebas in jenis:
        set_mode(token, key, "auto")
        st_typed, d_typed, _ = buat("BEBAS-999")
        st_auto, d_auto, no_auto = buat()
        _s, pol = call("GET", f"/api/doc-number-policy?key={key}", token)
        pola = (pol or {}).get("pola") or "^$"
        if st_typed != 400 or "tidak boleh diketik" not in det(d_typed).lower():
            rusak.append(f"{label}: mode OTOMATIS masih menerima nomor ketikan "
                         f"(HTTP {st_typed} {det(d_typed)[:70]})")
        if st_auto != 200 or not no_auto:
            rusak.append(f"{label}: pembuatan otomatis gagal (HTTP {st_auto} {det(d_auto)[:80]})")
        elif not re.match(pola, no_auto):
            rusak.append(f"{label}: nomor otomatis '{no_auto}' tidak mengikuti format owner "
                         f"({(pol or {}).get('format')})")

        set_mode(token, key, "manual")
        st_empty, d_empty, _ = buat()
        st_free, d_free, _ = buat(nomor_bebas)
        st_good, d_good, no_good = buat(nomor_benar)
        st_dup, d_dup, _ = buat(nomor_benar)
        if st_empty != 400 or "wajib diisi" not in det(d_empty).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor kosong (HTTP {st_empty})")
        if st_free != 400 or "tidak mengikuti pola" not in det(d_free).lower():
            rusak.append(f"{label}: mode MANUAL menerima nomor berpola bebas "
                         f"(HTTP {st_free} {det(d_free)[:70]})")
        if st_good != 200 or no_good != nomor_benar:
            rusak.append(f"{label}: nomor manual yang BENAR ditolak "
                         f"(HTTP {st_good} {det(d_good)[:90]})")
        if st_dup != 409:
            rusak.append(f"{label}: nomor manual kembar diterima (HTTP {st_dup} "
                         f"{det(d_dup)[:70]})")
        set_mode(token, key, "auto")
        bukti.append(f"{label}: otomatis→{no_auto} · manual→{no_good}")

    if not rusak:
        ok("G8", "3 jenis baru ditegakkan pada dokumen sungguhan: otomatis menolak ketikan, "
                 "manual menolak kosong/pola bebas/nomor kembar", " · ".join(bukti))
    else:
        bad("G8", "penomoran 3 jenis baru belum ditegakkan sebagaimana mestinya",
            "; ".join(rusak))


def cleanup(db, token):
    n = db.dewi_kasbon_requests.delete_many({"purpose": MARK}).deleted_count
    n += db.dewi_kasbon_requests.delete_many({"reason": MARK}).deleted_count
    set_mode(token, KASBON_KEY, "auto")
    db.counters.delete_many({"_id": {"$regex": r"^autonum:dewi_kasbon_requests:request_number:"}})
    # SESI #19 — dokumen uji tiga jenis baru + counter-nya (counter disemai ulang dari
    # nomor tertinggi yang MASIH ada, jadi menghapusnya tidak menimbulkan nomor kembar).
    baru = db.wh_delivery_notes.delete_many({"notes": MARK}).deleted_count
    baru += db.dewi_procurement_requests.delete_many({"title": MARK}).deleted_count
    je_uji = [j.get("je_number") for j in db.rahaza_journal_entries.find({"memo": MARK}, {"je_number": 1})]
    baru += db.rahaza_journal_entries.delete_many({"memo": MARK}).deleted_count
    if je_uji:
        db.rahaza_journal_lines.delete_many({"je_number": {"$in": je_uji}})
    for coll, field in (("wh_delivery_notes", "sj_number"),
                        ("dewi_procurement_requests", "request_number"),
                        ("rahaza_journal_entries", "je_number")):
        db.counters.delete_many({"_id": {"$regex": rf"^autonum:{coll}:{field}:"}})
    for key in ("wh_delivery_notes.sj_number", "dewi_procurement_requests.request_number",
                "rahaza_journal_entries.je_number"):
        set_mode(token, key, "auto")
    print(f"\n{Y}  bersih-bersih: {n} pengajuan kasbon + {baru} dokumen uji (SJ/PR/JE) dihapus · "
          f"semua mode dikembalikan ke otomatis{X}")


def main():
    print(f"{C}{B}FASE G (lanjutan) — setelan penomoran tidak boleh berbohong (INV-F25){X}")
    db = db_handle()
    part_static()
    st, d = call("POST", "/api/auth/login", None,
                 {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
                  "password": os.environ.get("ADMIN_PASS", "Admin@123")})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}  ✗ login gagal (HTTP {st}){X}")
        return 2
    try:
        part_runtime(token, db)
        part_runtime_baru(token, db)
    except Exception as e:  # noqa: BLE001
        bad("RUNTIME", "invarian runtime gagal dijalankan", str(e))
    finally:
        cleanup(db, token)
    print()
    if FAIL:
        print(f"{R}{B}VERDICT MERAH — {len(FAIL)} invarian gagal: {', '.join(FAIL)}{X}")
        return 1
    print(f"{G}{B}VERDICT HIJAU — {len(PASS)} invarian penomoran dokumen terjaga{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
