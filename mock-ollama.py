#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOCK OLLAMA - Mode Demo untuk Kilat AI
=========================================
Server palsu yang meniru Ollama (tanpa AI sungguhan) supaya Anda bisa
mencoba semua fitur Kilat AI - termasuk Mode Arena - sebelum mengunduh
model sungguhan.

Cara pakai:
    python mock-ollama.py
Lalu jalankan app.py di terminal lain.

Tiga model palsu tersedia: demo-nano, demo-mini, demo-pro
(semua jawaban hanya simulasi). Tekan Ctrl+C untuk berhenti.
"""

import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("MOCK_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOCK_PORT", "11434"))

MODELS = [
    {
        "name": "demo-nano",
        "model": "demo-nano",
        "size": 800_000_000,
        "details": {"parameter_size": "Demo-1B", "family": "mock"},
    },
    {
        "name": "demo-mini",
        "model": "demo-mini",
        "size": 2_100_000_000,
        "details": {"parameter_size": "Demo-3B", "family": "mock"},
    },
    {
        "name": "demo-pro",
        "model": "demo-pro",
        "size": 4_800_000_000,
        "details": {"parameter_size": "Demo-8B", "family": "mock"},
    },
]

SAMPLE_CATATAN = """=== CATATAN HARIAN ===
Hari ini:

Pagi
- [ ] Sarapan sehat
- [ ] Cek pesan & email
- [ ] Rencanakan 3 prioritas hari ini

Siang
- [ ] Kerja fokus 2 jam (matikan notifikasi)
- [ ] Istirahat 15 menit setiap sesi

Malam
- [ ] Baca 10 halaman buku
- [ ] Tulis 3 hal yang disyukuri hari ini
- [ ] Rencanakan besok

---
Dibuat otomatis oleh Kilat AI (mode demo).
"""

SAMPLE_PUISI = """Hujan Bogor

Gerimis turun menyapa kota hujan,
membasuh letih di ujung senja;
angin berbisik di antara pohon-pohon,
sementara aku menunggu - dan gerimis,
pelan-pelan, menjawab.

---
Dibuat otomatis oleh Kilat AI (mode demo).
"""

SAMPLE_BELANJA = """DAFTAR BELANJA
===============
- [ ] Beras 5 kg
- [ ] Telur 1 kg
- [ ] Minyak goreng 1 L
- [ ] Gula 1 kg
- [ ] Kopi
- [ ] Buah untuk seminggu

---
Dibuat otomatis oleh Kilat AI (mode demo).
"""


LAPORAN = """# Laporan Posisi Kas — Demo

**Periode:** Oktober 2026 | **Dibuat:** otomatis oleh Kilat AI (mode demo)

## Ringkasan

| Akun | Mata Uang | Saldo |
|---|---|---|
| Kas IDR | IDR | Rp 2.450.000.000 |
| Bank BCA operasional | IDR | Rp 8.730.500.000 |
| Bank Mandiri payroll | IDR | Rp 1.920.000.000 |
| Escrow USD | USD | 350.000 |

## Sorotan

- Arus masuk 7 hari: **Rp 750.000.000** (pelunasan piutang PT Abadi)
- Arus keluar terbesar: payroll periode Oktober Rp 412.500.000
- Posisi kas IDR gabungan: **Rp 13.100.500.000**

## Rekomendasi

1. Cukup likuiditas untuk payroll gelombang 2 (est. Rp 400 juta)
2. Pertimbangkan deposito untuk kas menganggur > Rp 2 M

---
> ⚠️ Laporan demo dari `mock-ollama.py` - di kondisi nyata, AI menyusun laporan
> dari data plugin treasury Anda lalu menyimpannya di sini.
"""


def intro(model):
    return (
        "Halo! Saya **%s**, salah satu model *palsu* di mode demo Kilat AI.\n\n"
        "Jawaban saya ini cuma simulasi dari `mock-ollama.py`, bukan AI sungguhan.\n\n"
        "**Cara mendapat AI beneran (gratis & offline):**\n"
        "1. Pasang Ollama dari https://ollama.com\n"
        "2. Jalankan `ollama pull qwen3:8b`\n"
        "3. Buka lagi aplikasi ini dan pilih model itu\n\n"
        "Panduan lengkap ada di file **PANDUAN.md**. Coba juga **Mode Arena**: klik "
        "tombol \U0001f3df\ufe0f di kanan atas, pilih beberapa model, lalu tanya sesuatu - "
        "semua model menjawab dan juri memilih yang terbaik. Atau minta saya: "
        "*\"buatkan file catatan.txt\"* / *\"lihat file workspace\"*." % model
    )


def generic(model, orig):
    if model == "demo-nano":
        return (
            "**%s** (demo) - versi singkat: saya cuma simulasi, belum bisa menjawab "
            "\"%s\".\n\nUntuk AI beneran: `ollama pull qwen3:8b`." % (model, orig)
        )
    if model == "demo-pro":
        return (
            "**%s** (demo) - versi \"pro\", tapi tetap simulasi \u26a1\n\n"
            "> \"%s\"\n\n"
            "Belum bisa dijawab sungguhan, tapi ini langkahnya:\n"
            "1. Pasang Ollama (https://ollama.com)\n"
            "2. `ollama pull qwen3:8b` (RAM 16 GB) atau `qwen3:4b` (RAM 8 GB)\n"
            "3. Pilih model itu di aplikasi - atau nyalakan **Mode Arena** untuk "
            "membandingkan beberapa model sekaligus\n\n"
            "Sementara itu, coba: *\"buatkan file catatan.txt\"*, *\"lihat file "
            "workspace\"*, atau pertanyaan matematika ke `deepseek-r1`." % (model, orig)
        )
    return (
        "Ini **mode demo** \u26a1 - saya skrip kecil pengganti Ollama (%s), bukan AI "
        "sungguhan, jadi belum bisa menjawab pertanyaan Anda.\n\n"
        "> \"%s\"\n\n"
        "**Untuk jawaban sungguhan** (gratis, offline, privat):\n"
        "1. Pasang Ollama dari https://ollama.com\n"
        "2. Jalankan `ollama pull qwen3:8b`\n"
        "3. Buka lagi aplikasi ini dan pilih model itu\n\n"
        "Sementara itu, coba: *\"buatkan file catatan.txt\"*, *\"tulis puisi lalu "
        "simpan ke file\"*, atau *\"lihat file workspace\"* \U0001f609" % (model, orig)
    )


def judge_answer(text):
    """Simulasi model juri: pilih kandidat dengan isi terpanjang."""
    blocks = re.findall(
        r"\[([A-H])\]\s*model:\s*(\S+)\n([\s\S]*?)(?=\n\n---|\Z)", text
    )
    if not blocks:
        return (
            "text",
            "JAWABAN TERBAIK: A\nALASAN: Hanya ada satu kandidat yang bisa dinilai "
            "(simulasi juri demo).",
        )
    best = max(blocks, key=lambda b: len(b[2].strip()))
    letter, model, _ = best
    return (
        "text",
        "JAWABAN TERBAIK: %s\nALASAN: Jawaban %s (%s) paling lengkap dan jelas di "
        "antara para kandidat. (Ini keputusan juri simulasi mode demo.)"
        % (letter, letter, model),
    )


def decide(body):
    """Tentukan balasan demo berdasarkan isi pesan terakhir."""
    model = str(body.get("model") or "demo-mini")
    msgs = body.get("messages") or []

    # 0) Permintaan dari model JURI (Mode Arena)
    last_user = ""
    for m in reversed(msgs):
        if m.get("role") == "user" and m.get("content"):
            last_user = str(m["content"])
            break
    if "JAWABAN TERBAIK" in last_user and "[A]" in last_user:
        return judge_answer(last_user)

    # 0.5) Debug: perlihatkan konteks sistem yang diterima (uji PENGETAHUAN.md)
    if re.search(r"debug konteks|ulangi konteks", str((msgs[-1] or {}).get("content") or ""), re.I):
        sysmsg = next((str(m.get("content")) for m in msgs if m.get("role") == "system"), "(tidak ada)")
        return ("text", "KONTEKS SISTEM YANG SAYA TERIMA:\n\n" + sysmsg[:1500])

    last = msgs[-1] if msgs else {}
    text = str(last.get("content") or "").lower()

    # 1) Baru saja menerima hasil tool -> beri jawaban akhir
    if last.get("role") == "tool":
        c = str(last.get("content") or "")
        if "files in workspace" in c.lower():
            lines = [l for l in c.split("\n")[1:] if l.strip()]
            listing = "\n".join("- `%s`" % l.strip().lstrip("- ") for l in lines) or "- (kosong)"
            return (
                "text",
                "Ini isi folder **workspace** Anda sekarang:\n\n%s\n\n"
                "Buka panel \U0001f4c1 Workspace di kanan atas untuk melihat filenya.\n\n"
                "> Mode demo: jawaban simulasi dari `mock-ollama.py`." % listing,
            )
        if "BERHASIL MENCATAT PENGAJUAN" in c:
            return (
                "text",
                "\u2705 Pengajuan sudah saya catat:\n\n```\n"
                + c[:600]
                + "\n```\n\nPenting: ini hanya **pencatatan** (maker). Eksekusi pembayaran "
                "tetap menunggu persetujuan **checker** - AI tidak pernah mengeksekusi "
                "pembayaran secara otomatis.",
            )
        if (
            "SALDO AKUN TREASURY" in c
            or "KURS REFERENSI" in c
            or "TRANSAKSI TERAKHIR" in c
            or "PENGAJUAN" in c
        ):
            return (
                "text",
                "Berikut datanya dari **aplikasi treasury** (via plugin):\n\n```\n%s\n```\n\n"
                "> Ingat: ini data **demo** dari `plugins/contoh-treasury.py`. Di kondisi "
                "nyata, plugin ini yang memanggil API/database aplikasi treasury Anda." % c[:900],
            )
        return (
            "text",
            "Berhasil! File sudah dibuat di folder `workspace/` - buka panel "
            "\U0001f4c1 Workspace di kanan atas untuk melihatnya, lalu klik filenya.\n\n"
            "> Catatan: ini **mode demo** (jawaban simulasi). Untuk AI beneran, "
            "pasang Ollama seperti di **PANDUAN.md**.",
        )

    # 1.5) Pertanyaan soal treasury -> panggil tool plugin
    t = str(last.get("content") or "").lower()
    if re.search(r"\b(buat|bikin|tulis|generate|susun)\w*\b", t) and "laporan" in t:
        return ("tool", "write_file", {"file_path": "laporan-posisi-kas.md", "content": LAPORAN})
    if re.search(r"\b(catat|ajukan|input|entry)\w*\b", t) and re.search(r"pengajuan|pembayaran", t):
        return (
            "tool",
            "treasury_catat_pengajuan",
            {
                "keterangan": t[:80],
                "akun": "BCA-OPR-102",
                "nominal": 150000000,
                "mata_uang": "IDR",
            },
        )
    if re.search(r"daftar pengajuan|pengajuan (yang )?(tertunda|tercatat|saja)", t):
        return ("tool", "treasury_daftar_pengajuan", {})
    if re.search(r"saldo|posisi kas|dana tersedia", t):
        return ("tool", "treasury_saldo", {})
    if re.search(r"\bkurs\b|nilai tukar", t):
        return ("tool", "treasury_kurs", {})
    if re.search(r"transaksi|mutasi|riwayat pembayaran", t):
        return ("tool", "treasury_transaksi", {"limit": 5})

    # 2) Permintaan MEMBUAT file -> tool write_file
    if re.search(r"\b(buat|bikin|tulis|simpan|save|write)", text) and re.search(
        r"(file|catatan|note|dokumen|puisi|belanja|rencana)", text
    ):
        if "belanja" in text:
            return ("tool", "write_file", {"file_path": "daftar-belanja.txt", "content": SAMPLE_BELANJA})
        if "puisi" in text:
            return ("tool", "write_file", {"file_path": "puisi.txt", "content": SAMPLE_PUISI})
        return ("tool", "write_file", {"file_path": "catatan.txt", "content": SAMPLE_CATATAN})

    # 3) Permintaan MELIHAT file -> tool list_files
    if re.search(r"\b(lihat|tampilkan|daftar|list|baca|isi|cek)\w*\b", text) and re.search(
        r"\b(file|files|workspace|folder)\b", text
    ):
        return ("tool", "list_files", {})

    # 4) Sapaan / pertanyaan tentang asisten
    if re.search(r"\b(siapa|halo|hai|hello|hi|perkenalkan|apa itu arena|kamu apa)\b", text):
        return ("text", intro(model))

    # 5) Lainnya -> jawaban generik sesuai "model"
    orig = last_user[:140]
    return ("text", generic(model, orig))


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # senyap

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _line(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.wfile.flush()

    def do_GET(self):
        if self.path.rstrip("/") == "/api/tags":
            self._json({"models": MODELS})
        elif self.path.rstrip("/") == "/api/version":
            self._json({"version": "0.0.0-demo"})
        else:
            self._json({"error": "not found"}, 404)

    def _cloud_chat(self, body):
        """Endpoint kompatibel OpenAI (SSE) untuk menguji Mode Cloud tanpa internet."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        model = str(body.get("model") or "cloud-demo")
        kind = decide(body)
        if kind[0] == "text":
            text = kind[1]
        else:
            text = (
                "Ini simulasi **Mode Cloud** \u2601\ufe0f (model `%s`).\n\n"
                "Di aplikasi sungguhan, sekarang ini pertanyaan Anda diteruskan ke "
                "penyedia API (OpenRouter/OpenAI/Groq/dll.) dan jawabannya mengalir "
                "ke sini. Tools dan Mode Arena nonaktif saat cloud dipakai.\n\n"
                "> Demo ini berjalan tanpa internet - servernya `mock-ollama.py`." % model
            )

        def sse(obj):
            self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        try:
            for i in range(0, len(text), 18):
                sse({"id": "demo", "model": model,
                     "choices": [{"index": 0, "delta": {"content": text[i:i + 18]}}]})
                time.sleep(0.02)
            sse({"id": "demo", "model": model,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
            self.wfile.write(b"data: [DONE]\n\n")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _anthropic_chat(self, body):
        """Simulasi API native Anthropic (SSE) untuk menguji Mode Cloud tanpa internet."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        model = str(body.get("model") or "claude-opus-5-5")
        system = str(body.get("system") or "")
        kind = decide(body)
        if kind[0] == "text":
            text = kind[1]
        else:
            text = "Simulasi **Mode Cloud via API Anthropic** (model `%s`)." % model

        def sse(ev_type, obj):
            obj2 = dict(obj)
            obj2["type"] = ev_type
            self.wfile.write(
                ("event: %s\ndata: %s\n\n" % (ev_type, json.dumps(obj2))).encode("utf-8")
            )
            self.wfile.flush()

        try:
            sse("message_start", {"message": {"model": model}})
            sse("content_block_start", {"index": 0, "content_block": {"type": "text"}})
            for i in range(0, len(text), 18):
                sse("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": text[i:i + 18]}})
                time.sleep(0.02)
            sse("content_block_stop", {"index": 0})
            sse("message_delta", {"delta": {"stop_reason": "end_turn"}})
            sse("message_stop", {})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._json({"error": "bad request"}, 400)
            return
        p = self.path.rstrip("/")
        if p == "/v1/chat/completions":
            self._cloud_chat(body)
            return
        if p == "/v1/messages" or p.endswith("/v1/messages"):
            self._anthropic_chat(body)
            return
        if p != "/api/chat":
            self._json({"error": "not found"}, 404)
            return

        model = str(body.get("model") or "demo-mini")

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        def tok(c):
            self._line({"model": model, "message": {"role": "assistant", "content": c}, "done": False})

        try:
            kind = decide(body)
            if kind[0] == "text":
                words = kind[1].split(" ")
                buf = ""
                for w in words:
                    buf += w + " "
                    if len(buf) >= 14 or w.endswith("\n"):
                        tok(buf)
                        buf = ""
                        time.sleep(0.02)
                if buf:
                    tok(buf)
            else:
                tok("Tentu! Sebentar ya, saya kerjakan dulu...\n\n")
                self._line(
                    {
                        "model": model,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {"function": {"name": kind[1], "arguments": kind[2]}}
                            ],
                        },
                        "done": False,
                    }
                )
            self._line(
                {
                    "model": model,
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "total_duration": 1,
                }
            )
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    try:
        srv = ThreadingHTTPServer((HOST, PORT), MockHandler)
    except OSError:
        print("ERROR: port %d sudah dipakai." % PORT)
        print("Mungkin Ollama asli sedang berjalan? Kalau iya, Anda tidak perlu")
        print("mode demo ini - langsung jalankan: python app.py")
        sys.exit(1)
    print("Mock Ollama (MODE DEMO) berjalan di http://%s:%d" % (HOST, PORT))
    print("Model palsu: %s" % ", ".join(m["name"] for m in MODELS))
    print("(jawaban simulasi, bukan AI sungguhan - cocok untuk mencoba Mode Arena)")
    print("Biarkan jendela ini terbuka, lalu jalankan 'python app.py' di terminal lain.")
    print("Tekan Ctrl+C untuk berhenti.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nMock Ollama berhenti.")


if __name__ == "__main__":
    main()
