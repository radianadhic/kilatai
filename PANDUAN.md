# ⚡ Panduan Kilat AI

**Kilat AI** adalah asisten AI "agentic" yang berjalan **100% di komputer Anda sendiri** — tanpa internet, tanpa langganan, tanpa data yang keluar. Anda bisa chat, dan AI bisa **membuat serta membaca file** di folder workspace.

> Ini proyek tiruan pribadi yang terinspirasi arena.ai — **tidak berafiliasi** dengan situs aslinya. Kode arena.ai asli tidak dibagikan ke publik, jadi ini aplikasi buatan sendiri dengan fitur serupa.

---

## 📦 Isi folder

| File | Fungsi |
|---|---|
| `app.py` | Aplikasi utama (satu file, tanpa instalasi tambahan) |
| `storage.py` | Lapisan penyimpanan: SQLite (database) + Valkey (cache & antrean event) |
| `mock-ollama.py` | Mode demo — coba semua fitur tanpa unduh model |
| `Mulai-Kilat.bat` | Tombol mulai untuk Windows (pakai Ollama asli) |
| `Mulai-Demo.bat` | Tombol mulai untuk Windows (mode demo) |
| `contoh-embed.html` | Contoh halaman web dengan widget Kilat tersemat — buka lewat `/demo` atau langsung dari file |
| `Dockerfile` + `docker-compose.yml` | Menjalankan Kilat AI + Ollama via Docker (opsional, lihat bagian 🐳) |
| `PENGETAHUAN.md` | Konteks aplikasi Anda (fitur, istilah, SOP) yang otomatis diketahui AI |
| `plugins/contoh-treasury.py` | Contoh plugin: memberi AI akses ke data aplikasi treasury (demo) |
| `PANDUAN.md` | File ini |
| `workspace/` | Folder tempat AI menyimpan file (dibuat otomatis) |

---

## ✅ Yang Anda butuhkan

| Kebutuhan | Keterangan |
|---|---|
| Python 3.8+ | Cek di terminal/CMD: `python --version`. Windows: install dari **Microsoft Store** (cari "Python 3") atau [python.org](https://python.org) |
| [Ollama](https://ollama.com) | Penghubung ke model AI lokal — gratis |
| RAM 8 GB | Minimum untuk model kecil — lihat detail di bagian hardware di bawah ⬇️ |

---

## 🖥️ Kebutuhan hardware (penting!)

Aplikasi Kilat AI sendiri sangat ringan — hampir semua komputer bisa menjalankannya. Yang menentukan adalah **model AI** yang dijalankan Ollama.

**Prinsip dasar:** model dimuat *seluruhnya* ke RAM/VRAM saat dipakai, jadi:

> **RAM/VRAM yang dibutuhkan ≈ ukuran file model + 2–4 GB** (untuk Windows, browser, dan konteks percakapan)

Makin besar model → makin pintar, tapi makin laparkan memori.

### Pilih model sesuai RAM

| Model | Unduhan | RAM minimal | RAM nyaman | Cocok untuk |
|---|---|---|---|---|
| `llama3.2:1b` / `phi4-mini` | ±1–1,3 GB | 4 GB | 8 GB | Komputer lama |
| `qwen3:4b` / `llama3.2:3b` | ±2–2,6 GB | 8 GB | 8–16 GB | Default awal |
| `qwen3:8b` / `gemma3:12b` | ±5–8 GB | 12 GB | **16 GB** | **Sweet spot** 👍 |
| `qwen3:14b` | ±9 GB | 24 GB | 24–32 GB | Kualitas tinggi |
| `qwen3:32b` | ±20 GB | 32 GB | 32–48 GB | Pengguna serius |
| `llama3.1:70b` | ±43 GB | 64 GB | 64 GB+ | Kelas server |

### Per komponen

- **RAM — paling menentukan.** Kalau kurang, komputer jadi sangat lambat (swap ke disk). Cek dulu sebelum memilih model.
- **GPU — opsional, tapi 5–20× lebih cepat.**
  - **NVIDIA** (GTX 10-series ke atas): langsung kedeteksi Ollama. VRAM 6 GB → model 3B; 8 GB (RTX 3060/4060) → model 7–8B; 24 GB → model 32B
  - **AMD**: hanya sebagian kartu (RX 6000/7000-an), kadang perlu pengaturan ekstra
  - **Tanpa GPU tetap bisa!** Model jalan di RAM lewat CPU — cukup untuk chat, hanya lebih pelan
  - **Mac M1–M4**: salah satu yang terbaik (memori terpadu). Mac 8 GB → model 3B, 16 GB → model 7–8B
- **CPU — hampir semua cukup.** Processor ±10 tahun terakhir (Intel Core, AMD Ryzen) sudah mendukung. Kecepatan CPU baru terasa kalau tidak pakai GPU.
- **Penyimpanan — SSD lebih nyaman.** Model tersimpan permanen (Windows: `C:\Users\namaAnda\.ollama\models`). Sediakan ruang kosong 10–20 GB. HDD = loading awal lama; SSD = cepat.

### Perkiraan kecepatan (model 7–8B)

| Setup | Token/detik | Terasa seperti |
|---|---|---|
| GPU VRAM 8 GB (RTX 3060/4060) | 30–60 | ⚡ Sangat lancar |
| Mac M1/M2 16 GB | 15–25 | ✅ Lancar |
| CPU modern tanpa GPU | 3–8 | 🙂 Seperti orang mengetik pelan — cukup sabar |

*(Model kecil 3B di CPU modern: 8–15 token/detik — masih nyaman.)*

### Rekomendasi cepat

1. **RAM 8 GB** → `qwen3:4b` atau `llama3.2:3b`. Chat enak; mode agen (membuat file) kadang gagal — tutup aplikasi lain saat dipakai.
2. **RAM 16 GB** (dengan/atau tanpa GPU 6–8 GB) → `qwen3:8b` atau `gemma3:12b`. **Sweet spot** — mode agen andal, jawaban jauh lebih cerdas.
3. **Mac Apple Silicon** → langsung `qwen3:8b`.
4. **RAM 32 GB / GPU 12 GB+** → `qwen3:14b`, kualitas mendekati AI berbayar untuk banyak tugas.

### Cara cek spesifikasi komputer

- **Windows**: `Ctrl + Shift + Esc` → tab **Performa** → lihat **Memori** dan **GPU**. Atau Settings → System → About
- **Mac**: klik logo  → **Tentang Mac Ini**
- **Linux**: `free -h` (RAM) dan `nvidia-smi` (GPU NVIDIA)

---

## 🚀 Langkah memasang (± 10 menit, sekali saja)

### 1. Pasang Ollama
1. Buka **https://ollama.com/download**
2. Unduh installer untuk Windows/Mac/Linux, instal seperti biasa (next → next → finish)
3. Setelah terpasang, Ollama berjalan otomatis di latar belakang (ada ikon **unta** 🦙 di pojok/taskbar)

### 2. Unduh model AI (sekali saja)
Buka **CMD** (Windows: tekan `Win + R`, ketik `cmd`, Enter), lalu ketik salah satu:

```bash
ollama pull qwen3:4b      # RAM 8 GB — ringan, ±2,6 GB
ollama pull qwen3:8b      # RAM 16 GB — rekomendasi utama, ±5 GB
ollama pull gemma3:12b    # alternatif dari Google, ±8 GB
```

Tunggu sampai 100% (kecepatan tergantung internet Anda). Daftar model rekomendasi lengkap ada di bagian **🤖 Rekomendasi model** di bawah ⬇️

### 3. Jalankan Kilat AI
- **Windows:** dobel-klik **`Mulai-Kilat.bat`**
- **Mac/Linux:** buka terminal di folder ini, jalankan `python3 app.py`

Browser akan terbuka otomatis di **http://localhost:8080**. (Kalau tidak, buka manual.)

### 4. Mulai chat! 🎉
- Pilih model di dropdown atas
- Ketik pesan, tekan **Enter**
- Coba: *"Buatkan file catatan.txt berisi rencana harian saya"* → lalu klik tombol **📁 Workspace** untuk melihat filenya

---

## 🎭 Mode Demo (tanpa Ollama, tanpa unduh apa pun)

Ingin lihat tampilannya dulu sebelum pasang Ollama?

- **Windows:** dobel-klik **`Mulai-Demo.bat`**
- **Mac/Linux:** jalankan dua terminal:
  1. `python3 mock-ollama.py`
  2. `python3 app.py`
- Di aplikasi, pilih model **demo-nano / demo-mini / demo-pro**

⚠️ Jawaban di mode demo hanya **simulasi** (skrip kecil), bukan AI sungguhan — tapi Anda bisa merasakan alur chat, pembuatan file, panel Workspace, dan bahkan Mode Arena.

---

## 🧰 Fitur

- 💬 **Chat streaming** dengan Markdown & blok kode (ada tombol Salin)
- 🏟️ **Mode Arena** — satu pertanyaan dijawab 2–4 model sekaligus, model juri memilih jawaban terbaik
- 🗂️ **Riwayat obrolan** — tersimpan di browser Anda (localStorage)
- 🔧 **Mode agen** — AI bisa `write_file`, `read_file`, `list_files` di folder `workspace/`
- 📝 **Laporan via chat** — minta AI membuat laporan → tersimpan sebagai file Markdown/HTML → viewer menampilkan hasil render
- ⌨️ **Entry data via chat** — AI bisa mencatat data (contoh: pengajuan pembayaran treasury) dengan pola maker-checker
- 🎤 **Input suara** — tombol mic; opsional 100% offline via whisper.cpp
- 🔊 **Bacakan jawaban** — text-to-speech lokal di setiap balasan AI
- 📤 **Upload file** — tarik & lepas file ke jendela aplikasi, atau tombol 📥 di panel Workspace (maks 5 MB)
- ☁️ **Mode Cloud (opsional)** — hubungkan API key kompatibel OpenAI sebagai cadangan
- 🌗 **Tema terang/gelap** — tombol bulan/matahari di kanan atas
- 🏢 **Integrasi aplikasi internal** — plugin `plugins/*.py` memberi AI akses ke data/fungsi aplikasi Anda; `PENGETAHUAN.md` memberi AI konteks aplikasi
- 📁 **Panel Workspace** — lihat, baca, dan unduh file buatan AI
- ⚙️ **Pengaturan** — system prompt, temperature, alamat Ollama, on/off tools

---

## 🤖 Rekomendasi model (open source & gratis)

Semua model di bawah bisa diunduh gratis lewat Ollama dan berjalan offline.

**Keluarga model utama:**

| Keluarga | Pembuat | Lisensi | Kekuatan |
|---|---|---|---|
| **Qwen3** ⭐ | Alibaba | Apache 2.0 | Juara umum: chat, coding, reasoning, multibahasa, panggil tools — cocok untuk mode agen |
| **Gemma 3** | Google | Gemma Terms* | Multimodal (paham gambar), ramah laptop |
| **Llama 3.x / 4** | Meta | Community* | Ekosistem terbesar, kualitas mapan |
| **DeepSeek R1** | DeepSeek | MIT | Raja reasoning & matematika (jawaban lebih panjang, "berpikir" dulu) |
| **Phi-4 / phi4-mini** | Microsoft | MIT | Kecil tapi pintar, jalan di komputer lawas |
| **Mistral / Devstral** | Mistral AI | Apache 2.0 | Devstral unggul untuk agen coding |
| **gpt-oss** | OpenAI | Apache 2.0 | Model "terbuka" pertama OpenAI (20b & 120b) |

\* = *open weights*: gratis untuk pemakaian pribadi/komersial normal, tapi ada syarat tambahan (mis. Llama: batas 700 juta pengguna aktif). Apache 2.0 & MIT = paling bebas tanpa syarat.

**Perintah unduh per kapasitas RAM:**

```bash
# RAM 8 GB
ollama pull qwen3:4b         # pilihan utama
ollama pull llama3.2:3b      # alternatif ringan
ollama pull phi4-mini        # paling enteng

# RAM 16 GB (sweet spot)
ollama pull qwen3:8b         # rekomendasi utama — jago panggil tools (mode agen)
ollama pull gemma3:12b       # alternatif multimodal
ollama pull deepseek-r1:8b   # khusus logika/matematika
ollama pull gpt-oss:20b      # model terbuka dari OpenAI

# RAM 24–32 GB / GPU besar
ollama pull qwen3:14b        # kualitas naik signifikan
ollama pull qwen3:30b        # MoE — cerdas tapi efisien
ollama pull gemma3:27b       # salah satu terbaik satu-GPU
ollama pull deepseek-r1:32b  # reasoning kelas atas
```

Katalog lengkap + ukuran unduhan: [ollama.com/library](https://ollama.com/library)

> 💡 Dunia model bergerak sangat cepat — selalu cek ollama.com/library untuk model terbaru.

### 🏔️ Ingin kelas Claude Opus/Fable?

Model frontier seperti **Claude Fable 5.1 / Opus 5.5** bersifat *proprietary* — bobotnya tidak bisa diunduh, jadi **tidak ada cara memakainya 100% offline**. Dua pilihan realistis:

1. **Persis sama → Mode Cloud**: sambungkan API Anthropic atau OpenRouter (lihat bagian ☁️). Harga Opus 5.5 sekitar $4 per juta token input / $20 output.
2. **Mendekati, offline → model open-weight terbesar yang komputer Anda sanggup jalankan.** Per Oktober 2026, urutan yang terdekat ke frontier:

| Model | Lisensi | Ukuran (total/aktif) | Skor terdekat | Hardware minimal |
|---|---|---|---|---|
| **MiMo-V2.6-Pro** (Xiaomi) | MIT | 1,02T / 42B | #1 open-weight (AA 46 vs Opus 58) | ~8× GPU server (±574 GB) |
| **GLM-5.3** (Z.ai) | custom | 753B / 40B | AA 45; coding paling dekat | ~8× H200 |
| **Kimi K3** (Moonshot) | custom | 2,8T / 104B | Juara Arena kelas open (Elo ±1.486) | ≥610 GB RAM (khusus rak server) |
| **DeepSeek V4-Flash** | MIT | 552B / 16B | AA ±40; 1M konteks | ±110–162 GB RAM (kuantisasi 3–4 bit) |
| **GLM-5.3-Flash** | MIT | 320B / 18B | AA ±42; paling "terjangkau" di kelas ini | 3–4× GPU 80 GB |
| Kelas konsumen 24 GB GPU | — | Qwen3-32B, DeepSeek-R1-32B | jauh dari Opus, tapi terbaik di kelasnya | GPU 24 GB / Mac 32 GB |

**Fakta jujur:** di benchmark coding jaraknya tipis (SWE-bench ±93–96% vs 97% milik frontier), tapi kecerdasan umumnya masih tertinggal ±12 poin — dan model peringkat atas butuh hardware kelas server (puluhan–ratusan GB memori).

**💡 Jembatan offline untuk model besar:** banyak model raksasa ini (DeepSeek V4-Flash, Kimi K3, MiMo) **tidak tersedia lokal di Ollama** (tag-nya hanya mengarah ke cloud Ollama). Jalankan lewat **LM Studio / llama.cpp / vLLM** di komputer yang sanggup, lalu di Kilat AI aktifkan **Mode Cloud dengan base URL lokal** mis. `http://localhost:1234/v1` — percakapan tetap 100% di jaringan Anda, tanpa internet.

---

## 🏟️ Mode Arena — tanya semua model, ambil yang terbaik

Fitur khas Kilat AI: **satu pertanyaan dijawab beberapa model sekaligus**, lalu **model juri** menilai dan memilih jawaban terbaik untuk Anda 🏆.

**Cara pakai:**
1. Klik tombol **🏟️ Arena** di kanan atas
2. **Peserta sudah tercentang otomatis** — aplikasi memilih rekomendasi terbaik dari model yang terpasang (bertanda ⭐), lengkap dengan perkiraan kebutuhan RAM per model. Tombol **⭐ Pakai rekomendasi** mengembalikan pilihan default kapan pun
3. Pilih juri (default-nya juga rekomendasi terbaik), klik Simpan (chip berubah jadi **Arena: ON**), lalu chat seperti biasa
4. Setiap model menjawab satu per satu → juri memberi vonis → jawaban terbaik ditandai hijau 🏆
5. Tidak setuju dengan juri? Klik **👍 Pilih** di jawaban yang menurut Anda terbaik

**Catatan penting:**
- Saat Mode Arena aktif, tools (buat file) nonaktif — mode ini khusus membandingkan kualitas jawaban
- Model dijalankan **bergantian** agar RAM aman — Anda tidak butuh RAM untuk semua model sekaligus, hanya untuk model terbesar yang dipilih
- Juri adalah model lokal juga — bisa keliru atau memihak jawabannya sendiri; kalau juri gagal memutuskan, Anda tinggal memilih manual
- Cocok untuk menentukan model mana yang paling cocok dengan gaya ngobrol Anda sebelum mendownload model besar

### Resep 3 LLM gratis & open-source (100% offline)

Mode Arena menerima 2–4 model peserta + 1 juri — semua gratis. Model dijalankan **bergantian** dan otomatis **di-unload tiap giliran** (keep_alive 0), jadi RAM hanya perlu menampung **model terbesar**, bukan jumlah ketiganya.

| RAM Anda | 3 model peserta | Juri |
|---|---|---|
| 8 GB | `qwen3:4b` + `llama3.2:3b` + `phi4-mini` | `qwen3:4b` |
| 16 GB ⭐ | `qwen3:8b` + `gemma3:12b` + `deepseek-r1:8b` | `qwen3:8b` |
| 24 GB+ / GPU besar | `qwen3:14b` + `gemma3:27b` + `deepseek-r1:14b` | `qwen3:14b` |

Unduh trio pilihan Anda (contoh kelas 16 GB), lalu buka 🏟️ Arena → centang ketiganya → pilih juri → Simpan:

```bash
ollama pull qwen3:8b && ollama pull gemma3:12b && ollama pull deepseek-r1:8b
```

Catatan:
- `deepseek-r1` "berpikir" dulu sebelum menjawab — di Arena jawabannya lebih panjang & lambat; itu wajar
- **Hindari model bertanda "cloud"** di ollama.com (mis. `deepseek-v4-flash`) — tag itu meneruskan permintaan ke server Ollama (butuh internet, tidak lokal)
- Juri bisa memihak jawabannya sendiri; kalau tidak setuju, klik **👍 Pilih** pada jawaban yang Anda suka
- Ingin lebih dari 3? Maksimal 4 peserta — tapi makin banyak model, makin lama menunggu

---

## 📤 Upload file ke workspace

Anda bisa menaruh file sendiri ke workspace agar bisa dibaca AI:

- **Tarik & lepas** (drag & drop) file apa pun ke jendela aplikasi, **atau**
- Buka panel **📁 Workspace** → klik tombol **📥** di pojoknya

Ketentuan: maksimal **5 MB per file**. Setelah terupload, minta AI membacanya, misalnya: *"baca file laporan.txt lalu buatkan ringkasan"*.

> ⚠️ AI hanya bisa **membaca file teks** (txt, md, csv, kode, json, dll.). File biner seperti PDF/Word/gambar bisa tersimpan di workspace, tetapi isinya tidak bisa dibaca AI.

---

## 🗣️ Suara, laporan & entry data via chat

### 📝 Membuat laporan via chat

Cukup minta lewat chat, misalnya: *"buatkan laporan posisi kas bulan ini"*. AI menyusun laporannya dan menyimpan sebagai file Markdown (`.md`) atau HTML di workspace. Klik filenya di panel **📁 Workspace** — viewer kini menampilkan **hasil render** yang rapi (tabel, heading, dsb.), dengan tombol **"Lihat mentah"** untuk beralih ke teks aslinya.

### ⌨️ Entry data via chat

AI bisa mencatat data ke aplikasi lewat plugin — contoh sudah aktif (mode demo):

- *"catat pengajuan pembayaran 150 juta untuk supplier PT Cahaya"* → plugin `treasury_catat_pengajuan` menulis entri ber-ID & waktu berstatus **MENUNGGU PERSETUJUAN (checker)** ke `workspace/pengajuan-demo.json`
- *"tampilkan daftar pengajuan"* → menampilkan semua entri + statusnya

**Aturan aman untuk entry data finansial (WAJIB):**
1. AI hanya **mencatat** (maker) — tidak pernah mengeksekusi pembayaran/transfer
2. Pertahankan alur **maker-checker**: AI pencatat, manusia pemberi persetujuan
3. Setiap entri punya ID & waktu untuk jejak audit
4. Produksi: sambungkan plugin ke API aplikasi treasury Anda (bukan file JSON demo)

### 🎤 Input suara (mic)

Klik tombol **🎤** di samping tombol kirim, bicara (Bahasa Indonesia), klik lagi untuk berhenti — teks otomatis masuk kotak pesan lalu bisa Anda edit dulu sebelum dikirim.

Dua mode:
- **Default — speech recognition bawaan browser** (Chrome/Edge). ⚠️ *Jujur:* engine Chrome memroses audio di cloud → **butuh internet** dan tidak cocok untuk data rahasia. Firefox belum mendukung.
- **100% offline — whisper.cpp** (opsional, lanjutan): pasang [whisper.cpp server](https://github.com/ggml-org/whisper.cpp) di komputer/lokal, jalankan `ARENA_WHISPER_URL="http://127.0.0.1:8081/inference" python app.py`, lalu isi alamat yang sama di ⚙️ Pengaturan → *Server Whisper*. Audio diproses lokal, hasil teks masuk ke kotak pesan.

### 🔊 Membacakan jawaban

Tombol **🔊 Bacakan** di bawah setiap jawaban AI akan membacakannya (text-to-speech bawaan sistem — offline; suara Bahasa Indonesia dipakai otomatis bila tersedia di OS). Klik lagi untuk berhenti.

---

## ☁️ Mode Cloud (opsional)

Kalau komputer Anda terasa berat untuk model lokal, Anda bisa menghubungkan **API key** dari penyedia mana pun yang kompatibel dengan format OpenAI, plus **API Anthropic (Claude) yang didukung native**:

| Penyedia | Base URL | Catatan |
|---|---|---|
| [OpenRouter](https://openrouter.ai) | `https://openrouter.ai/v1` | **Rekomendasi** — satu key untuk ratusan model, ada model gratis |
| [Anthropic](https://platform.claude.com) | `https://api.anthropic.com` | Claude **Opus 5.5** (`claude-opus-5-5`, $4/$20 per juta token) & **Fable 5.1** (`claude-fable-5-1`, $10/$50) — dideteksi otomatis |
| [OpenAI](https://platform.openai.com) | `https://api.openai.com/v1` | mis. model `gpt-4o-mini` |
| [Groq](https://console.groq.com) | `https://api.groq.com/openai/v1` | ada tier gratis, sangat cepat |
| LM Studio (lokal!) | `http://localhost:1234/v1` | server model lokal ber-GUI, tetap 100% offline |

**Cara pakai:** ⚙️ Pengaturan → centang **Mode Cloud** → isi base URL, API key, dan nama model → Simpan. Untuk kembali ke mode lokal, cukup hapus centangnya.

**Batasan & peringatan:**
- ⚠️ Saat cloud aktif, **percakapan keluar dari komputer Anda** ke penyedia API — privasi lokal tidak berlaku (ada indikator di aplikasi)
- Tools (buat file) dan Mode Arena nonaktif selama cloud dipakai
- API key tersimpan di browser Anda (localStorage) dan hanya dikirim ke server `app.py` lokal

---

## 🌗 Tema terang/gelap

Klik tombol **bulan/matahari** 🌙 di kanan atas untuk berganti tema. Pilihan Anda diingat otomatis.

---

## 🔗 Embed di website

Kilat AI bisa **disematkan di website apa pun** — sebagai widget melayang, iframe, atau dipanggil lewat API.

**Cara 1 — Widget melayang (paling mudah).** Tambahkan satu baris ke HTML website Anda sebelum `</body>`:

```html
<script src="http://ALAMAT-SERVER:8080/widget.js" defer></script>
```

Muncul tombol ⚡ di pojok halaman; klik → panel chat terbuka. Opsi: `data-side="left"` untuk posisi kiri, `data-key="..."` bila server memakai embed key.

**Cara 2 — Iframe langsung** (chat permanen di dalam halaman):

```html
<iframe src="http://ALAMAT-SERVER:8080/embed"
        style="width:100%;max-width:420px;height:560px;border:0;border-radius:14px"
        title="Chat Kilat AI"></iframe>
```

**Cara 3 — API** (untuk aplikasi lain): `POST http://ALAMAT:8080/api/chat` dengan body JSON `{"model":"...","messages":[...]}` — balasan NDJSON streaming (`{"t":"token",...}` per potongan, diakhiri `{"t":"done"}`).

**Mencoba sekarang:** jalankan aplikasi lalu buka `http://localhost:8080/demo` — halaman contoh dengan widget hidup + cuplikan kode siap salin.

**Hal penting sebelum dipublikasikan:**
- ⚠️ **Server harus menyala** — pengunjung chat langsung ke komputer/server yang menjalankan `app.py`
- **Website HTTPS tidak bisa memuat widget HTTP** (diblokir browser). Untuk situs publik, sajikan Kilat AI lewat HTTPS juga (reverse proxy, Cloudflare Tunnel, atau hosting Python)
- **Hanya untuk jaringan rumah (LAN)?** Ganti `localhost` dengan IP komputer Anda (mis. `http://192.168.1.10:8080`) dan jalankan dengan `ARENA_HOST=0.0.0.0` — hanya perangkat satu Wi-Fi yang bisa akses
- **Keamanan saat publik:** aktifkan **embed key** (lihat sub-bagian 🔑 di bawah) dan batasi asal API dengan `ARENA_ALLOWED_ORIGINS=https://situsanda.com`
- Banyak host PHP/Python murah bisa menjalankan `app.py` — unggah filenya, set port, selesai

### 🔑 Membuat dan memakai embed key

Embed key adalah **kata sandi buatan sendiri** — tidak perlu mendaftar ke mana pun. Fungsinya: menolak panggilan API dari website/pihak yang tidak Anda izinkan.

**Langkah 1 — buat kuncinya** (pilih salah satu):
- Jalankan di terminal/CMD: `python -c "import secrets; print(secrets.token_urlsafe(24))"` → salin hasilnya, atau
- Buat manual: minimal 20 karakter, campuran huruf besar/kecil/angka — hindari kata umum & tanggal lahir

**Langkah 2 — aktifkan di server** (pilih salah satu):
- **Cara file (termudah):** buat file bernama `KUNCI-EMBED.txt` di folder kilat-ai, isinya **satu baris** kunci Anda. Hapus file ini untuk menonaktifkan.
- **Cara variabel lingkungan:**
  - Windows CMD: `set ARENA_EMBED_KEY=kunci-anda` lalu `python app.py`
  - Mac/Linux: `ARENA_EMBED_KEY=kunci-anda python3 app.py`

**Langkah 3 — restart `app.py`.** Di jendela terminal akan muncul: `Kunci embed : AKTIF`

**Langkah 4 — pakai kunci di sisi website:**
- Widget: `<script src="http://ALAMAT:8080/widget.js" data-key="kunci-anda" defer></script>`
- Iframe: `http://ALAMAT:8080/embed?key=kunci-anda`
- API langsung: tambahkan header `X-Embed-Key: kunci-anda`

**Bagaimana aturannya:**
- Tanpa kunci di server → semua origin diperbolehkan (default, cocok untuk pemakaian pribadi/LAN)
- Dengan kunci → ditolak (403) kecuali: membawa `X-Embed-Key` yang benar, berasal dari localhost, atau dari halaman milik server Kilat AI sendiri (UI & iframe `/embed` tetap jalan normal)

**Jujur soal batasannya:** kunci yang tertanam di HTML widget bisa dilihat pengunjung yang membedah kode halaman Anda — anggap ini **gerbang pagar, bukan lemari besi**: efektif menahan bot dan pemakai acak, bukan penjahat yang tekun. Untuk proteksi lebih ketat, gabungkan dengan `ARENA_ALLOWED_ORIGINS` dan jangan pajak model berat di internet terbuka.

---

## 🏢 Integrasi ke aplikasi internal (studi kasus: treasury)

**Pertanyaan umum: kalau Kilat AI di-embed di aplikasi treasury, apakah AI bisa mendeteksi data & fitur aplikasi itu sendiri?**

**Jawaban jujur: TIDAK — dan itu disengaja demi keamanan.** AI (widget/iframe) hidup di "ruang kaca" terpisah; ia hanya tahu apa yang *dikirim* kepadanya. Ia tidak bisa melihat database, layar, atau internal aplikasi treasury. Agar AI "mengenal" aplikasi Anda, Anda harus menyuplai konteksnya lewat 3 lapis berikut:

**Lapis 1 — `PENGETAHUAN.md` (fitur, istilah, SOP).** Edit file ini: deskripsikan aplikasi, fitur-fiturnya, istilah internal (RTGS, netting, maker-checker...), dan aturan menjawab. Isinya otomatis disisipkan ke ingatan AI di setiap percakapan mode agen — berlaku langsung tanpa restart. (Contoh yang ada sekarang: konteks treasury.)

**Lapis 2 — `plugins/*.py` (data & fungsi live).** Ini cara AI "mengambil" data treasury sungguhan saat ditanya. Lihat `plugins/contoh-treasury.py`:
- `TOOLS` = daftar kemampuan yang diperkenalkan ke AI (mis. `treasury_saldo`, `treasury_kurs`, `treasury_transaksi`)
- `handle()` = kode yang dijalankan saat AI memanggilnya — **di kondisi nyata, ganti isinya dengan panggilan ke API/database aplikasi treasury Anda (read-only!)**
- Plugin hanya aktif di aplikasi utama (mode agen); widget embed dan Mode Cloud tidak mendapat tools ini (pengaman bawaan)

**Lapis 3 — dokumen di workspace.** Upload SOP/manual/glosarium ke `workspace/`, lalu AI bisa membacanya dengan `read_file` saat menjawab.

**Arsitektur yang disarankan:**
```
Aplikasi Treasury ──(API internal read-only)──> plugins/xxx.py ──> app.py ──> Ollama
                                                        │
PENGETAHUAN.md ──────────(konteks otomatis)─────────────┘
```

**Aturan keamanan untuk data finansial (WAJIB):**
1. **Read-only** — plugin cukup bisa MEMBACA; jangan beri AI hak menulis/mengeksekusi pembayaran
2. **Least privilege** — pakai akun khusus baca-saja dengan cakupan data seminimal mungkin
3. **AI bisa mengarang** — wajibkan (lewat PENGETAHUAN.md) AI menyebut sumber & tanggal setiap angka; angka finansial selalu diverifikasi manusia
4. **Audit** — catat siapa bertanya apa (log app.py sudah mencatat request)
5. **Rahasia** — jangan taruh data sensitif permanen di PENGETAHUAN.md/workspace

---

## 📴 Pasang tanpa internet sama sekali (offline total)

Kilat AI + Ollama memang dirancang untuk itu — **tidak ada komponen yang butuh internet**, kecuali saat mengunduh installer & model. Untuk komputer/nas yang terisolasi (air-gapped):

**1. Siapkan di komputer lain yang ada internet:**
- Unduh installer Ollama: https://ollama.com/download
- Unduh modelnya: `ollama pull qwen3:8b` (atau model pilihan Anda)
- Unduh/salin folder `kilat-ai` (atau `KilatAI.zip`)

**2. Transfer via USB ke komputer offline:**
- Installer Ollama → jalankan di komputer offline (installer tidak butuh internet)
- Model → salin **seluruh folder**:
  - Windows: `C:\Users\namaAnda\.ollama\models`
  - Linux: `~/.ollama/models` (atau `/usr/share/ollama/.ollama/models`)
  
  ke path yang sama persis di komputer offline. Cek dengan `ollama list` — model akan muncul.
- Alternatif model: unduh file **GGUF** dari Hugging Face, salin via USB, lalu di komputer offline buat `Modelfile` berisi `FROM ./model.gguf` dan jalankan `ollama create namamodel -f Modelfile`

**3. Di komputer offline:** jalankan `Mulai-Kilat.bat` (atau `python app.py`) — selesai. Matikan Mode Cloud (default memang mati).

**Konsekuensi offline:** pengetahuan model terbatas pada data latihnya (tidak bisa cari info baru) — jadi penyisipan `PENGETAHUAN.md` + dokumen di workspace menjadi **makin penting** untuk menjawab pertanyaan spesifik perusahaan Anda.

---

## 🗄️ Penyimpanan data (gaya platform AI modern)

Kilat AI menyimpan data secara **berlapis**, meniru arsitektur platform AI besar dalam skala lokal — tanpa Redis:

| Lapisan | Implementasi | Isi |
|---|---|---|
| **Database relasional** | SQLite (`data/kilat.db`) | Percakapan, pesan, **jejak audit** (tool yang dipanggil, file yang ditulis) |
| **Cache & antrean event** | **Valkey** (pengganti Redis) | Cache daftar model/file (TTL singkat) + antrean event audit `events:audit` (1000 terakhir) |
| **Object storage** | Folder `workspace/` | File buatan AI & upload |
| **Cadangan lokal** | localStorage browser | Riwayat tetap ada walau server mati (fallback otomatis) |

**Konsep pentingnya:**
- **Riwayat chat kini tersimpan di server** (SQLite) — bukan hanya di browser. Buka dari browser/perangkat mana pun di jaringan yang sama, riwayatnya tetap ada. localStorage otomatis jadi cadangan bila server tidak terjangkau.
- **Valkey bersifat opsional** — kalau tidak berjalan, semua fitur tetap bekerja (cache dilewati, event hanya masuk SQLite). Tidak ada yang rusak.
- **Jejak audit** setiap aksi agen (tool dipanggil, file ditulis/diupload, percakapan disimpan/dihapus) tercatat di tabel `audit` + antrean Valkey — penting untuk kepatuhan treasury.

**Menjalankan Valkey (opsional tapi disarankan):**
```bash
# Debian/Ubuntu: sudo apt-get install -y valkey-server
valkey-server                        # default port 6379
# atau via Docker: docker run -p 6379:6379 valkey/valkey
```
Lalu jalankan aplikasi seperti biasa — status "Valkey: terhubung" muncul di banner terminal.

**Variabel lingkungan:**

| Variabel | Default | Fungsi |
|---|---|---|
| `ARENA_DB_PATH` | `data/kilat.db` | Lokasi file database SQLite |
| `ARENA_VALKEY_URL` | `redis://127.0.0.1:6379` | Alamat server Valkey |

**Backup & migrasi:** cukup salin `data/kilat.db` + folder `workspace/` — itu seluruh data Anda.

**Kenapa Valkey, bukan Kafka?** Valkey adalah fork komunitas Redis (protokol sama, ringan, satu binari kecil) — pas untuk cache & antrean aplikasi lokal. Kafka adalah platform *event streaming* terdistribusi ber-JVM (ratusan MB, desain untuk aliran event lintas sistem skala besar) — overkill untuk aplikasi desktop/server kecil, tapi cocok di lapisan infrastruktur perusahaan jika kelak sistem treasury Anda butuh aliran event lintas aplikasi. Arsitektur `storage.py` sengaja modular: fungsi `event_valkey()` bisa diganti producer Kafka tanpa menyentuh bagian aplikasi lain.

---

## 🐳 Docker (opsional, untuk yang terbiasa)

Kilat AI bisa dijalankan lewat Docker — image-nya **sangat ringan** karena aplikasi murni Python stdlib (tanpa `pip install`). Ada dua mode:

**Mode LENGKAP — Kilat AI + Ollama sekalian dalam container** (paling simpel, tidak perlu install Ollama di host):

```bash
docker compose up -d --build        # bangun & jalankan
# ambil model (tersimpan di docker volume, tidak hilang saat container dibuat ulang):
docker compose exec ollama ollama pull qwen3:8b
```

Buka **http://localhost:8080** — selesai.

**Mode HEMAT — Ollama sudah terpasang di komputer** (model tidak perlu diunduh ulang):
1. Edit `docker-compose.yml`: hapus/comment service `ollama` + volumes `ollama-models`, hapus `depends_on`
2. Ganti `ARENA_OLLAMA` menjadi `http://host.docker.internal:11434`
3. `docker compose up -d --build`

**Variabel lingkungan yang didukung:**

| Variabel | Fungsi | Default |
|---|---|---|
| `ARENA_OLLAMA` | Alamat server Ollama | `http://127.0.0.1:11434` |
| `ARENA_HOST` / `ARENA_PORT` | Alamat & port aplikasi | `127.0.0.1` / `8080` (di container: `0.0.0.0`) |
| `ARENA_EMBED_KEY` | Kunci embed untuk API publik | nonaktif |
| `ARENA_ALLOWED_ORIGINS` | Batasi origin API (CORS) | `*` |
| `ARENA_WHISPER_URL` | Server Whisper untuk input suara offline | nonaktif |

**Folder yang dipetakan (volume) — edit di host, langsung berlaku:**

| Folder host | Di container | Fungsi |
|---|---|---|
| `./workspace` | `/app/workspace` | File buatan AI |
| `./plugins` | `/app/plugins` | Plugin integrasi (restart container setelah mengubah) |
| `./PENGETAHUAN.md` | `/app/PENGETAHUAN.md` | Konteks aplikasi (langsung berlaku) |

**Catatan:**
- **Keamanan:** `KUNCI-EMBED.txt` sengaja dikecualikan dari image (`.dockerignore`) — kunci rahasia jangan dibakar ke dalam image; pakai `ARENA_EMBED_KEY` di environment
- **GPU:** Ollama dalam container jalan mode CPU secara default. Untuk GPU NVIDIA, pasang *nvidia-container-toolkit* di host lalu buka blok `deploy:` yang sudah disiapkan (comment) di `docker-compose.yml`
- **Linux + mode hemat:** jika `host.docker.internal` tidak ter-resolve, tambahkan di service kilat: `extra_hosts: ["host.docker.internal:host-gateway"]`

---

## 🔧 Masalah umum

| Gejala | Solusi |
|---|---|
| "Ollama tidak terdeteksi" | Buka aplikasi Ollama (ikon 🦙), atau jalankan `ollama serve` di terminal, lalu tekan **Muat ulang** |
| "Belum ada model" | Jalankan `ollama pull qwen3:4b` dulu |
| `python` tidak dikenal (Windows) | Install dari Microsoft Store: buka Store → cari **Python 3.12** → Install. Atau coba `py app.py` |
| Port 8080 terpakai | Aplikasi otomatis pindah ke 8081–8089 — lihat alamatnya di jendela terminal |
| Jawaban lambat / terputus-putus | Model terlalu besar untuk komputer Anda → pakai model lebih kecil (`qwen3:4b`) |
| AI tidak mau membuat file | Model kecil kurang andal memanggil tools. Coba `qwen3:8b` atau lebih besar, atau matikan-nyalakan tombol 🔧 Tools |
| Mode Arena terasa lambat | Normal — tiap model menjawab bergantian. Kurangi jumlah model peserta, atau pakai model yang lebih kecil |
| Cloud: "API key ditolak (401)" | Key salah/kadaluarsa — periksa ulang di Pengaturan → Cloud |
| Cloud: "Model tidak ditemukan (404)" | Nama model salah — cek penulisan (mis. `openai/gpt-4o-mini`, bukan `gpt4o`) |
| Cloud: "Kuota/limit tercapai (429)" | Tunggu sebentar, atau ganti model/penyedia |
| Upload ditolak | Maksimal 5 MB per file |
| Widget tidak muncul di website | Server Kilat AI sedang jalan? Alamat `widget.js` benar? Situs HTTPS tidak bisa memuat `http://` (mixed content) |
| Chat widget error di HP pengunjung | HP harus bisa menjangkau alamat server — satu Wi-Fi untuk LAN, atau publikasikan server |
| “Ditolak: embed key salah atau tidak ada” (403) | Server memakai kunci — sertakan `data-key="..."` di tag script widget, atau `?key=...` di iframe, atau header `X-Embed-Key` di API. Atau hapus `KUNCI-EMBED.txt` untuk menonaktifkan |
| Model tidak muncul setelah pindah via USB | Folder `.ollama/models` harus tersalin utuh ke path yang sama di komputer offline; cek `ollama list` |
| Plugin tidak terbaca | File harus di folder `plugins/`, berekstensi `.py`, dan mendefinisikan `TOOLS` + `handle()` — lihat pesan di jendela terminal saat startup |
| Tombol 🎤 tidak berfungsi | Pakai Chrome/Edge; izinkan akses mikrofon saat diminta; engine browser butuh internet — untuk offline pasang whisper.cpp |
| "Server Whisper belum dikonfigurasi" | Isi alamat whisper.cpp di Pengaturan → Server Whisper DAN jalankan app.py dengan `ARENA_WHISPER_URL` yang sama |
| Container tidak bisa konek Ollama di host | Mode hemat di Linux: tambah `extra_hosts: ["host.docker.internal:host-gateway"]`; atau pakai mode lengkap (Ollama ikut container) |
| Model di container Ollama hilang | Tidak akan hilang selama docker volume `ollama-models` tidak dihapus (`docker volume rm` = hapus model) |

---

## 🔒 Privasi

Semua percakapan hanya mengalir: **browser → app.py → Ollama**, semuanya di komputer Anda. Tidak ada yang dikirim ke internet. Riwayat chat tersimpan di browser (localStorage) dan file buatan AI di folder `workspace/`.

Pengecualian: jika Anda mengaktifkan **Mode Cloud**, percakapan dikirim ke penyedia API yang Anda pilih — aplikasi akan selalu menampilkan indikator saat mode ini aktif.

---

## 🗑️ Menghapus sepenuhnya

1. Hapus folder `kilat-ai` ini
2. (Opsional) hapus model: `ollama rm qwen3:8b`
3. (Opsional) uninstall Ollama seperti aplikasi biasa

---

*Selamat mencoba! ⚡*
