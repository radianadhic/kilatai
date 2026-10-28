# ============================================================
# Kilat AI - Dockerfile
# Image sangat ringan: aplikasi murni Python stdlib (tanpa pip).
# Build  : docker build -t kilat-ai .
# Jalankan: docker run -p 8080:8080 kilat-ai
# Lengkap: lihat docker-compose.yml ( Kilat AI + Ollama sekaligus )
# ============================================================
FROM python:3.12-slim

WORKDIR /app

# Salin aplikasi (yang dikecualikan ada di .dockerignore -
# termasuk KUNCI-EMBED.txt agar kunci rahasia tidak ikut terkunci di image)
COPY app.py mock-ollama.py PANDUAN.md PENGETAHUAN.md contoh-embed.html logo.png ./
COPY plugins/ ./plugins/

# Konfigurasi default untuk container:
# - ARENA_HOST 0.0.0.0 wajib agar bisa diakses dari luar container
# - ARENA_OLLAMA menunjuk Ollama di komputer host (Docker Desktop).
#   Kalau memakai docker-compose dengan service "ollama", otomatis
#   tertimpa menjadi http://ollama:11434
ENV ARENA_HOST=0.0.0.0 \
    ARENA_PORT=8080 \
    ARENA_NO_OPEN=1 \
    ARENA_OLLAMA=http://host.docker.internal:11434

# Folder workspace untuk file buatan AI
RUN mkdir -p workspace

EXPOSE 8080

# Cek kesehatan sederhana (punyaman stdlib, tanpa curl/wget tambahan)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=4)" || exit 1

CMD ["python", "app.py"]
