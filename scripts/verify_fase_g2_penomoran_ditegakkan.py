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
NOT_ENFORCED_KEY = "rahaza_journal_entries.je_number"

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
    if not miss7:
        ok("G7", "LAYAR memakai kebijakan: form kasbon membaca kebijakan & layar admin jujur",
           "DocNumberField dipakai bersama; toggle mode hanya untuk yang ditegakkan")
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
                        "format": "JE-{YYYY}{MM}{DD}-{SEQ:4}", "active": True})
    cfg = db.doc_number_configs.find_one({"key": NOT_ENFORCED_KEY}, {"_id": 0}) or {}
    if (st_mode == 400 and st_m == 400 and "belum bisa diubah" in det(d_m).lower()
            and st_fmt == 200 and cfg.get("mode") in (None, "auto")):
        ok("G4", "jenis yang belum ditegakkan MENOLAK perubahan mode (setelan tidak berbohong), "
                 "format tetap boleh diubah",
           f"mode HTTP {st_m} · format HTTP {st_fmt} · tersimpan mode={cfg.get('mode')}")
    else:
        bad("G4", "setelan mode diterima untuk jenis yang tidak menegakkannya ⇒ setelan berbohong",
            f"mode HTTP {st_m} {det(d_m)[:110]} · format HTTP {st_fmt} · mode tersimpan={cfg.get('mode')}")


def cleanup(db, token):
    n = db.dewi_kasbon_requests.delete_many({"purpose": MARK}).deleted_count
    n += db.dewi_kasbon_requests.delete_many({"reason": MARK}).deleted_count
    set_mode(token, KASBON_KEY, "auto")
    db.counters.delete_many({"_id": {"$regex": r"^autonum:dewi_kasbon_requests:request_number:"}})
    print(f"\n{Y}  bersih-bersih: {n} pengajuan uji dihapus · mode kasbon dikembalikan ke otomatis{X}")


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
