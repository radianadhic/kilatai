# 🧪 Pengujian UI (Headless Chromium)

Suite pengujian fungsional otomatis untuk Kilat AI — membuka aplikasi di Chromium
headless, mengklik tombol sungguhan, dan memverifikasi perilaku DOM.

## Cara pakai

```bash
# 1. Install Chromium (Debian/Ubuntu)
sudo apt-get install -y chromium

# 2. Pasang dependensi pengujian (hanya puppeteer-core, kecil)
cd uitest && npm install puppeteer-core

# 3. Pastikan aplikasi + server demo berjalan (di terminal lain)
python3 mock-ollama.py &
python3 app.py &

# 4. Jalankan suite (sesuaikan jalur chromium bila berbeda)
node suite.js
```

## Isi

| File | Fungsi |
|---|---|
| `suite.js` | 18 pengujian end-to-end: modal (buka/tutup/simpan), Mode Arena (default tercentang, chip ON/OFF, 3 kartu jawaban + vonis juri), chat + tools, deteksi error JS |
| `diagnosa.js` | Diagnostik spesifik: memverifikasi `[hidden]` vs CSS (pernah jadi bug: `.overlay{display:flex}` mengalahkan atribut `hidden` — fixed dengan `[hidden]{display:none!important}`) |

> Catatan: `node_modules/` tidak di-commit (lihat .gitignore root).
