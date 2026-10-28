# -*- coding: utf-8 -*-
"""
CONTOH PLUGIN INTEGRASI APLIKASI TREASURY
=========================================
File ini menunjukkan cara memberi AI akses ke data/fungsi aplikasi treasury
Anda. Sekarang isinya DATA PALSU untuk demo. Di kondisi nyata, ganti isi
handle() dengan panggilan ke API / database aplikasi treasury Anda
(disarankan: akses READ-ONLY / baca saja).

Cara kerja:
- TOOLS   = daftar kemampuan yang diperkenalkan ke AI (format skema Ollama)
- handle() = fungsi yang dijalankan saat AI memanggil tool tersebut

Keamanan:
- Plugin berjalan dengan hak yang sama seperti app.py - hanya pasang plugin
  buatan tim Anda sendiri
- Berikan hak akses seminimal mungkin (baca saja), jangan pernah izinkan AI
  mengeksekusi pembayaran/penghapusan data tanpa persetujuan manusia
"""

import json
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# DATA CONTOH (di kondisi nyata: ganti dengan panggilan API/DB treasury)
# ---------------------------------------------------------------------------
SALDO = {
    "Kas IDR": {"akun": "KAS-IDR-001", "mata_uang": "IDR", "saldo": 2450000000},
    "Bank BCA operasional": {"akun": "BCA-OPR-102", "mata_uang": "IDR", "saldo": 8730500000},
    "Bank Mandiri payroll": {"akun": "MANDIRI-PAY-205", "mata_uang": "IDR", "saldo": 1920000000},
    "Escrow USD": {"akun": "ESCROW-USD-310", "mata_uang": "USD", "saldo": 350000},
}

KURS = {"USD/IDR": 15250, "EUR/IDR": 16600, "SGD/IDR": 11400, "JPY/IDR": 104}

TRANSAKSI = [
    {"tanggal": "2026-10-03", "tipe": "masuk", "akun": "BCA-OPR-102", "nominal": 750000000, "ket": "Pelunasan piutang PT Abadi"},
    {"tanggal": "2026-10-03", "tipe": "keluar", "akun": "MANDIRI-PAY-205", "nominal": 412500000, "ket": "Payroll periode Oktober (1/2)"},
    {"tanggal": "2026-10-02", "tipe": "keluar", "akun": "KAS-IDR-001", "nominal": 85000000, "ket": "Operasional kantor cabang"},
    {"tanggal": "2026-10-01", "tipe": "masuk", "akun": "ESCROW-USD-310", "nominal": 50000, "ket": "Setoran escrow proyek X"},
    {"tanggal": "2026-09-30", "tipe": "keluar", "akun": "BCA-OPR-102", "nominal": 225000000, "ket": "Pembayaran supplier PT Cahaya"},
]

# ---------------------------------------------------------------------------
# SKEMA TOOLS yang diperkenalkan ke AI
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "treasury_saldo",
            "description": (
                "Menampilkan daftar saldo semua akun kas/bank pada aplikasi "
                "treasury, beserta nomor akun, mata uang, dan nominalnya. "
                "Panggil saat pengguna bertanya tentang saldo, posisi kas, "
                "atau dana yang tersedia."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "treasury_kurs",
            "description": (
                "Menampilkan kurs referensi harian aplikasi treasury "
                "(mis. USD/IDR, EUR/IDR)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "treasury_transaksi",
            "description": (
                "Menampilkan transaksi terakhir pada aplikasi treasury "
                "(tanggal, masuk/keluar, akun, nominal, keterangan). "
                "Panggil saat pengguna bertanya tentang transaksi, mutasi, "
                "atau riwayat pembayaran."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Jumlah transaksi terbaru yang ditampilkan (default 5).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "treasury_catat_pengajuan",
            "description": (
                "Mencatat PENGAJUAN pembayaran baru ke aplikasi treasury "
                "(status awal: menunggu persetujuan checker). Ini PENCATATAN saja, "
                "BUKAN eksekusi pembayaran. Panggil saat pengguna meminta mencatat / "
                "mengajukan pembayaran atau entry data lewat chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keterangan": {
                        "type": "string",
                        "description": "Uraian pengajuan, mis. 'Pembayaran supplier PT X invoice 123'",
                    },
                    "akun": {"type": "string", "description": "Akun sumber dana, mis. 'BCA-OPR-102'"},
                    "nominal": {"type": "number", "description": "Nominal pengajuan"},
                    "mata_uang": {"type": "string", "description": "Mata uang, default IDR"},
                },
                "required": ["keterangan", "akun", "nominal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "treasury_daftar_pengajuan",
            "description": (
                "Menampilkan daftar pengajuan pembayaran yang sudah dicatat lewat "
                "chat beserta status persetujuannya."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ---------------------------------------------------------------------------
# HANDLER - dijalankan saat AI memanggil tool
# Di kondisi nyata, ganti isi tiap cabang dengan panggilan API/DB treasury,
# contoh:
#   import urllib.request, json
#   req = urllib.request.Request("http://server-treasury.internal/api/saldo",
#                                headers={"Authorization": "Bearer xxx"})
#   data = json.loads(urllib.request.urlopen(req, timeout=10).read())
# ---------------------------------------------------------------------------


def _fmt_rp(n):
    return "Rp {:,.0f}".format(n).replace(",", ".")


def _pengajuan_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "workspace", "pengajuan-demo.json"
    )


def _load_pengajuan():
    try:
        with open(_pengajuan_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_pengajuan(data):
    with open(_pengajuan_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def handle(name, args):
    args = args if isinstance(args, dict) else {}

    if name == "treasury_saldo":
        lines = ["SALDO AKUN TREASURY (data demo):"]
        total_idr = 0
        for nama, s in SALDO.items():
            if s["mata_uang"] == "IDR":
                lines.append("- %s (%s): %s" % (nama, s["akun"], _fmt_rp(s["saldo"])))
                total_idr += s["saldo"]
            else:
                lines.append("- %s (%s): %s %s" % (nama, s["akun"], s["saldo"], s["mata_uang"]))
        lines.append("Total setara IDR (akun IDR saja): %s" % _fmt_rp(total_idr))
        return "\n".join(lines)

    if name == "treasury_kurs":
        lines = ["KURS REFERENSI (data demo):"]
        for pair, rate in KURS.items():
            lines.append("- %s : %s" % (pair, _fmt_rp(rate)))
        return "\n".join(lines)

    if name == "treasury_transaksi":
        try:
            limit = int(args.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, len(TRANSAKSI)))
        lines = ["TRANSAKSI TERAKHIR (data demo):"]
        for t in TRANSAKSI[:limit]:
            nominal = _fmt_rp(t["nominal"]) if t["nominal"] < 10**9 else "%s (kemungkinan USD/asing)" % t["nominal"]
            lines.append(
                "- %s | %s | %s | %s | %s" % (t["tanggal"], t["tipe"].upper(), t["akun"], nominal, t["ket"])
            )
        return "\n".join(lines)

    if name == "treasury_catat_pengajuan":
        ket = str(args.get("keterangan") or "").strip() or "(tanpa keterangan)"
        akun = str(args.get("akun") or "").strip() or "-"
        try:
            nominal = float(args.get("nominal") or 0)
        except (TypeError, ValueError):
            nominal = 0
        cur = str(args.get("mata_uang") or "IDR").strip().upper() or "IDR"
        data = _load_pengajuan()
        ent = {
            "id": "PGJ-%04d" % (len(data) + 1),
            "waktu": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "keterangan": ket,
            "akun": akun,
            "nominal": nominal,
            "mata_uang": cur,
            "status": "MENUNGGU PERSETUJUAN (checker)",
        }
        data.append(ent)
        _save_pengajuan(data)
        return (
            "BERHASIL MENCATAT PENGAJUAN:\n"
            + json.dumps(ent, ensure_ascii=False, indent=1)
            + "\n\nCatatan: hanya pencatatan (maker) - pembayaran TIDAK dieksekusi. "
            "Menunggu persetujuan checker di aplikasi treasury."
        )

    if name == "treasury_daftar_pengajuan":
        data = _load_pengajuan()
        if not data:
            return "BELUM ADA PENGAJUAN yang tercatat (data demo kosong)."
        lines = ["DAFTAR PENGAJUAN (demo):"]
        for e in data:
            lines.append(
                "- %s | %s | %s | %s | %s %s | %s"
                % (e.get("id"), e.get("waktu"), str(e.get("keterangan"))[:40],
                   e.get("akun"), e.get("nominal"), e.get("mata_uang"), e.get("status"))
            )
        return "\n".join(lines)

    return "Tool tidak dikenal: %s" % name
