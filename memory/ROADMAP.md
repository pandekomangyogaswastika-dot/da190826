# ROADMAP — CV. Dewi Aditya ERP

## Produksi & Maklon — **5 CACAT LOGIKA DITUTUP 2026-06-18 (sesi #20)**
- ✅ Permak dari form manual OTOMATIS tertaut baris reject ⇒ permak berhasil menambah stok FG &
  sisa bisa kirim ke buyer (dulu hasil permak mustahil dikirim).
- ✅ Tombol **"+ Dispatch"**: pengiriman bertahap dilanjutkan pada surat jalan yang SAMA
  (`dispatch_seq` +1, nomor tetap) — bukan surat jalan baru tiap kali.
- ✅ Panel read-only **"Aksesoris dari BOM Katalog"** di form buat PO maklon, angkanya dari mesin
  yang sama dengan yang tersimpan di `po_accessories`.
- ✅ Vendor CMT punya tombol **"Buat Permintaan Pengganti"** (jalur lama sudah dimatikan HTTP 410).
- ✅ Surat jalan ANAK (pengganti) tidak membawa daftar aksesoris PO.
- Gate: **INV-F27** (`scripts/verify_permak_dispatch_aksesoris.py`, 9 invarian, termasuk pemeriksaan
  pintu di layar). Sisa yang belum diuji lewat alur nyata: surat jalan anak diuji dengan dokumen anak
  bentukan gate, **belum** lewat approval permintaan PENGGANTI ujung-ke-ujung (P2).

## Portal Gudang — **FASE H SELESAI 100%** (H-1 · H-2 · H-3 · H-4/H-9 · H-5 · H-6 · H-7 · H-8 ·
## H-6b — ditutup 2026-08-16 s/d 2026-08-17, sesi #14–#17)
- ✅ **H-6b (SELESAI 2026-08-17 #17 — penutup Fase H)** Laporan progres Cutting **MENERBITKAN
  dokumen "Pengeluaran Material"** (`ref_type='cutting_issue'`, `source='cutting'`, status langsung
  `issued`) + satu baris kartu stok, sehingga SELURUH arus keluar gudang (MI manual · BOM job
  internal · Kirim Material CMT · Cutting) tampil di SATU daftar yang bisa disaring per sumber.
  Stok **tidak** dipotong dua kali (dokumen hanya bukti atas mutasi yang sudah terjadi) dan
  **tidak** dijurnal (nilai kain BERPINDAH jadi nilai potongan; `post-to-gl` menolak dokumen
  cutting). Progres lama tanpa dokumen kelihatan di Portal Cutting + bisa diterbitkan retroaktif
  (idempoten). Gate: **INV-F24** (14 invarian).
- ✅ **H-5 (SELESAI 2026-08-16 #15)** Penerimaan kain menerbitkan **gulungan otomatis**
  (`RL-{YYYY}{MM}-{SEQ:4}`, nomor tidak boleh diketik), rincian roll divalidasi SEBELUM stok
  ditulis, dan penerimaan lama yang belum punya gulungan muncul di tab **"Penerimaan tanpa roll"**
  dengan tombol terbitkan retroaktif (idempoten). Gate: **INV-F22**.
- ✅ **H-6 (SELESAI 2026-08-16 #15)** Portal Cutting **WAJIB** menunjuk gulungan untuk kain yang
  dilacak per gulungan; pemakaian dibagi **FIFO** lewat satu pintu `core/fabric_roll_engine`
  (sisa roll + movement `issue` selalu ikut), dan kain yang belum punya gulungan ditolak dengan
  jalan keluarnya disebut. Gate: **INV-F22**.
  *(Catatan lingkup: dokumen **Material Issue** untuk arus keluar kain di Cutting — usul lama
  `ref_type='cutting_issue'` — SELESAI di sesi #17 (H-6b), lihat entri teratas.)*
- **H-7 (SELESAI 2026-08-16 #16)** ✅ Surat jalan **satu daftar lintas sumber** (read-only):
  `GET /api/wms/delivery-notes/sources` menyatukan `wh_delivery_notes` + `vendor_shipments` +
  dispatch buyer (dipecah per `dispatch_seq`), tiap baris mencetak PDF RESMI sumbernya, plus
  `sources/recap-pdf` (rekap landscape, 100% lebar halaman). Layar: tab "Semua Sumber" dengan chip
  filter sumber, rentang tanggal, CSV, Cetak Rekap, dan "Buka sumber". Gate: **INV-F23**.
- **H-8 (SELESAI 2026-08-16 #16)** ✅ Empat alias mati diarahkan ke pintu yang bekerja:
  `do-management` → `prod-shipments-vendor`; `prod-cmt-packing` & `maklon-packing` →
  `da-cmt-receive` (packing CMT = menerima FG + QC, koleksi `cmt_receipts`); `cmt-progress` →
  `cmt-monitor`. Gate: **INV-F23** (S7/S8 menolak alias yang menunjuk modul berkoleksi kosong).
- **F3/F4 (P1)** Rapikan 5 PDF tersering (SPP · Invoice · Slip Gaji · Picklist · SJ Vendor) ke pola
  `_pdf_data_table` (auto-wrap + penuh lebar halaman) seperti Surat Jalan Buyer di Fase F1/F2.
- ⚠️ **G (SEPARUH SELESAI 2026-08-17 #18)** Penomoran dokumen **Auto/Manual per jenis dokumen**
  yang bisa diatur System Admin. **8 jenis SUDAH ditegakkan**: SPP (PO Produksi) · PO Maklon ·
  Roll Kain · Penerimaan FG dari CMT (CMT-RCV) · Invoice Maklon (manual) · Invoice Piutang (AR) ·
  Pengajuan Kasbon · Pengajuan Pinjaman Karyawan. **41 jenis lain masih "Otomatis saja"** — dan
  layar+API kini MENGATAKANNYA terang-terangan (badge kuning + `PUT` mode ditolak) supaya setelan
  tidak berbohong. Gate: **INV-F21** (SPP) + **INV-F25** (penegakan + kejujuran setelan).
  Menyambungkan sisanya: tandai `policy_enforced` → `issue_number(..., requested=...)` di jalur
  tulis → pasang `<DocNumberField>` di form → daftarkan di `WRITE_PATHS` INV-F25.
- ✅ **D (SELESAI 2026-08-16 #16)** Dashboard Marketing: pintunya ada di sidebar Portal Marketing
  (Ringkasan & Laporan) dan angkanya **dari data hidup** — SSOT siklus marketing
  (`/api/marketing/cycle/overview`): target vs omzet, anggaran terpakai, ROAS/ROI (hanya diklaim
  sahih bila cakupan HPP ≥ 80%), papan "perlu perhatian", dan lingkup toko per pemakai.
  Total dihitung BACKEND (layar tidak menjumlah ulang). Gate: **INV-F20** (8 invarian).
  *(Entri lama "D (P0) belum didaftarkan di sidebar" sudah BASI — diperbaiki 2026-08-17 #18
  setelah diukur ulang: INV-F20 D1–D8 hijau.)*

## P0 (menunggu owner)
- **Kunci Anthropic**: isi `ANTHROPIC_API_KEY` di `backend/.env`. Sampai diisi, SEMUA fitur AI
  (Asisten ERP untuk pertanyaan kompleks, Prediksi Kas, Ringkasan Harian, Analitik SDM, Estimasi
  Produksi/Maklon) gagal dengan anggun tapi tidak berfungsi.
- **Isi kemasan 478 item** lewat Ekspor/Impor Excel — lihat `docs/PANDUAN_UOM_EXCEL.md`.
- **Rebase 91 item bersatuan kemasan** (74 rol · 14 pak · 3 lusin) —
  `scripts/uom_rebase_worklist.py --export` lalu isi 2 kolom.

## P1 (next)
- **Basis pengetahuan Asisten** belum mencakup Portal Vendor, Klien, dan LiveHost
  (12 dari 15 portal sudah ada di `backend/data/portal_kb/`).
- Rekonsiliasi lokasi stok aksesoris `int-demo-loc-1` → zona kanonik `ZN-AKS`
  (`scripts/migrate_stock_locations_to_wh.py`).
- Verifikasi email SUNGGUHAN (SMTP dummy `aiosmtpd` atau kredensial nyata) untuk membuktikan
  lampiran Excel+PDF rapor valuasi benar terkirim.
- Perluas Jest/RTL ke `AccessoryValuationAutomation` + `StokOpnameTab`.
- Deeper UAT of remaining advanced Finance modules via UI flows (frontend) — backend logic already
  validated 39/39. Candidates: Executive Report Hub, AI Cash Flow (needs EMERGENT_LLM_KEY), Bad Debt
  Write-off, Purchase Discount (AP), Settlement Queue.
- Seed demo data for Budget, GL-Mapping, Master Categories, Periods so modules show populated states.

## P2 (nice-to-have)
- Standardise trailing-slash policy (e.g. `/api/announcements` 307 redirect) app-wide.
- Document required query params (e.g. `/finance/reports/general-ledger` needs `account_code`).
- Batch operations (bulk approve/pay), email notifications for approvals, Excel export on all reports.

## Backlog / tech-debt
- Remove `*_backup.py` route files if confirmed unused (e.g. `dewi_accessories_full_backup.py`).
- Reduce remaining non-gating ruff findings (F401 unused imports) incrementally.

## Done sesi 2026-08-05 (lihat CHANGELOG entri teratas)
- ✅ **Pemilih satuan di layar untuk 6 titik masuk stok** — Penerimaan (scan-in), Opname aksesoris,
  Cutting (progres), Pengeluaran Material, Put-away, Opname gudang, plus Aksesoris masuk/keluar.
  Satu endpoint opsi satuan (`GET /api/rahaza/materials/uom-options`), satu komponen UI
  (`uom/UomPicker.jsx`), dan cakupan konversi diseragamkan lewat `core/bom_uom.factor_to_base`.
  Uji: `tests/flow_uom_entry_points_ui_test.py` 38/38.
- ✅ **Penomoran dokumen tahap 2** — 11 penghasil nomor manual dipusatkan ke
  `utils.counters.gen_prefixed_number`; katalog layar 34 → 45 jenis; peta manual 18 → 7 (sisanya bukan
  nomor dokumen). Uji: `tests/flow_doc_numbering_phase2_test.py` 19/19 (termasuk 25 nomor bersamaan → unik).
- ✅ **Dashboard Maklon** memakai `GET /api/prod/dashboard?business_type=maklon` — tab "Alur Produksi"
  + pintu menu `maklon-alur-produksi`, label akhir "Dispatch ke Buyer".
- ✅ **Sisa uji R&D UoM** — jalur simpan Sample Costing terbukti (`backend/tests/flow_rnd_uom_test.py` 38/38).

## Done (see CHANGELOG.md)
- **FASE 11 (2026-07-25)**: BUG-R11-A ditutup tuntas (46 endpoint · sweep 7.184 req → 0 error 500) ·
  BUG-4 `datetime` SUBCLASS `date` (3 file) · BUG-5 kode akun modul Aset tidak ada di CoA ·
  alias legacy `yarn_*` dihentikan penulisannya · 4 alat uji diperbaiki · gate.sh 9/9 HIJAU.
  Detail: `docs/PLAN_FASE11.md`.
- Finance flow/integration hardening + lint cleanup (2026-06-07).
- Light-mode portals, Announcement Board, business-process docs, first Finance test (2026-06-02).
