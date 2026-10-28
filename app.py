#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KILAT AI - Asisten AI "agentic" yang berjalan 100% di komputer Anda.

Tiruan pribadi yang terinspirasi arena.ai (tidak berafiliasi).
Butuh  : Python 3.8+ dan Ollama (https://ollama.com)
Cara   : python app.py  ->  buka http://localhost:8080
Tanpa  : pip install, database, atau internet.

Fitur  : chat streaming, riwayat obrolan, Markdown, agen bisa
         membuat/membaca file di folder workspace/, panel Workspace.
"""

import json
import os
import sys
import threading
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

import storage  # lapisan penyimpanan: SQLite (relasional) + Valkey (cache & event)

# ----------------------------------------------------------------------------
# Konfigurasi
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.join(BASE_DIR, "workspace")
PLUGIN_DIR = os.path.join(BASE_DIR, "plugins")       # tools tambahan per aplikasi
KNOWLEDGE_FILE = os.path.join(BASE_DIR, "PENGETAHUAN.md")  # konteks aplikasi
KNOWLEDGE_MAX = 6000
DEFAULT_OLLAMA = os.environ.get("ARENA_OLLAMA", "http://127.0.0.1:11434")
HOST = os.environ.get("ARENA_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARENA_PORT", "8080"))
NO_OPEN = os.environ.get("ARENA_NO_OPEN", "") == "1"

# Server Whisper (opsional) untuk input suara 100% offline (mis. whisper.cpp).
# Contoh: ARENA_WHISPER_URL="http://127.0.0.1:8081/inference"
WHISPER_URL = os.environ.get("ARENA_WHISPER_URL", "").strip()

# --- Penyimpanan gaya platform modern (opsional Valkey, wajib SQLite) ---
DB_PATH = os.environ.get("ARENA_DB_PATH") or os.path.join(BASE_DIR, "data", "kilat.db")
VALKEY_URL = os.environ.get("ARENA_VALKEY_URL") or "redis://127.0.0.1:6379"

# --- Untuk embed di website lain ---
# Asal (origin) yang diizinkan memanggil API. Default "*" (semua).
# Batasi misalnya: "https://situsanda.com,http://localhost:8080"
ALLOWED_ORIGINS = os.environ.get("ARENA_ALLOWED_ORIGINS", "*")
# Kunci opsional untuk melindungi API bila server dijangkau dari internet.
# Jika diisi, permintaan dari origin asing wajib membawa header X-Embed-Key.
# Cara mengisi: variabel lingkungan ARENA_EMBED_KEY, ATAU buat file
# KUNCI-EMBED.txt (satu baris berisi kunci) di samping app.py.
EMBED_KEY = os.environ.get("ARENA_EMBED_KEY", "").strip()
if not EMBED_KEY:
    try:
        _kf = os.path.join(BASE_DIR, "KUNCI-EMBED.txt")
        if os.path.isfile(_kf):
            with open(_kf, encoding="utf-8") as _fh:
                for _line in _fh:
                    _line = _line.strip()
                    if _line and not _line.startswith("#"):
                        EMBED_KEY = _line
                        break
    except OSError:
        pass

# Opener tanpa proxy supaya koneksi ke Ollama lokal tidak dialihkan proxy sistem
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

DEFAULT_SYSTEM = (
    'Kamu adalah asisten AI lokal bernama "Kilat AI" yang berjalan sepenuhnya '
    "di komputer pengguna melalui Ollama. Jawab selalu dalam Bahasa Indonesia yang "
    "jelas, ramah, dan terstruktur; gunakan Markdown bila membantu. Jika pengguna "
    "meminta membuat, menyimpan, membaca, atau melihat file, gunakan tools yang "
    "tersedia (write_file, read_file, list_files) - file tersimpan di folder "
    "workspace dan dapat dilihat pengguna lewat panel Workspace. Untuk pertanyaan "
    "biasa, jawab langsung tanpa tools. Jika permintaan kurang jelas, tanya balik "
    "dengan sopan."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write (create or overwrite) a text file in the user's workspace "
                "folder. Use whenever the user asks to create, make, save, or "
                "write a file. The user speaks Indonesian."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative file name, e.g. 'catatan.txt' or 'kode/app.py'",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to write into the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the text content of a file in the user's workspace folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative file name, e.g. 'catatan.txt'",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files that exist in the user's workspace folder.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ----------------------------------------------------------------------------
# Workspace & tools
# ----------------------------------------------------------------------------


def _load_plugins():
    """Muat plugins/*.py: tiap file mendefinisikan TOOLS (skema) + handle(name, args).

    KEAMANAN: kode plugin berjalan dengan hak yang sama dengan app.py - hanya
    pasang plugin dari sumber yang Anda percaya (buatan tim Anda sendiri).
    """
    plugins = []
    if not os.path.isdir(PLUGIN_DIR):
        return plugins
    import importlib.util

    for fn in sorted(os.listdir(PLUGIN_DIR)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        path = os.path.join(PLUGIN_DIR, fn)
        try:
            spec = importlib.util.spec_from_file_location("arena_plugin_" + fn[:-3], path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            tools = getattr(mod, "TOOLS", None) or []
            handle = getattr(mod, "handle", None)
            if tools and callable(handle):
                plugins.append({"file": fn, "tools": tools, "handle": handle})
            else:
                print('  [plugin] dilewati (butuh TOOLS + handle): %s' % fn)
        except Exception as e:
            print('  [plugin] GAGAL dimuat %s: %s' % (fn, e))
    return plugins


PLUGINS = []  # diisi saat main()


def load_knowledge():
    """Baca PENGETAHUAN.md (bila ada) untuk disisipkan ke system prompt.

    Isi file ini = deskripsi aplikasi Anda: fitur, istilah, SOP, aturan menjawab.
    Berlaku langsung tanpa restart (dibaca ulang tiap permintaan).
    """
    try:
        if os.path.isfile(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, encoding="utf-8") as fh:
                txt = fh.read().strip()
            if txt:
                return txt[:KNOWLEDGE_MAX]
    except OSError:
        pass
    return ""


def safe_path(rel):
    """Kembalikan path absolut yang aman di dalam folder workspace, atau None."""
    rel = str(rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    root = os.path.realpath(WORKSPACE)
    p = os.path.realpath(os.path.join(root, rel))
    if p != root and not p.startswith(root + os.sep):
        return None
    return p


def list_workspace():
    items = []
    if os.path.isdir(WORKSPACE):
        for root, _dirs, files in os.walk(WORKSPACE):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, WORKSPACE).replace(os.sep, "/")
                try:
                    items.append(
                        {
                            "name": rel,
                            "size": os.path.getsize(full),
                            "modified": int(os.path.getmtime(full)),
                        }
                    )
                except OSError:
                    pass
    items.sort(key=lambda x: x["name"])
    return items


def run_tool(name, args):
    """Jalankan tool agen. Kembalikan (ok, hasil_text)."""
    args = args if isinstance(args, dict) else {}
    try:
        if name == "list_files":
            files = list_workspace()
            if not files:
                return True, "Files in workspace: (empty - belum ada file)"
            lines = ["Files in workspace:"]
            for f in files:
                lines.append("- %s (%d bytes)" % (f["name"], f["size"]))
            return True, "\n".join(lines)

        if name == "read_file":
            p = safe_path(args.get("file_path"))
            if not p or not os.path.isfile(p):
                return False, "File tidak ditemukan: %s" % args.get("file_path")
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                return True, fh.read()[:50000]

        if name == "write_file":
            p = safe_path(args.get("file_path"))
            if not p:
                return False, "Nama file tidak valid."
            content = str(args.get("content", ""))
            if len(content) > 1000000:
                return False, "Isi file terlalu besar (maksimal 1 MB)."
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(content)
            rel = os.path.relpath(p, WORKSPACE).replace(os.sep, "/")
            storage.audit("tool.write_file", rel)
            storage.cache_invalidate("cache:files")
            return True, "Berhasil menulis file '%s' (%d karakter)." % (rel, len(content))

        # tool dari plugin (integrasi aplikasi lain, mis. treasury)
        for p in PLUGINS:
            for t in p["tools"]:
                if (t.get("function") or {}).get("name") == name:
                    try:
                        return True, str(p["handle"](name, args))[:8000]
                    except Exception as e:
                        return False, "Error plugin %s: %s" % (p["file"], e)

        return False, "Tool tidak dikenal: %s" % name
    except Exception as e:  # pragma: no cover
        return False, "Error saat menjalankan tool: %s" % e


# ----------------------------------------------------------------------------
# Ollama
# ----------------------------------------------------------------------------


class ChatError(Exception):
    pass


def ollama_stream(url, payload, timeout=600):
    """Generator yang mengalirkan chunk JSON (NDJSON) dari /api/chat Ollama."""
    req = urllib.request.Request(
        url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = _OPENER.open(req, timeout=timeout)
    try:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue
    finally:
        try:
            resp.close()  # menutup koneksi = membatalkan generasi di Ollama
        except Exception:
            pass


def _chat_anthropic(base, key, model, messages, temp, send):
    """Chat lewat API native Anthropic (Claude Messages API, streaming SSE).

    Dipakai untuk model seperti claude-opus-5-5 dan claude-fable-5-1.
    Aktif otomatis bila alamat API memuat kata "anthropic".
    """
    system = "\n\n".join(
        str(m.get("content") or "") for m in messages if m.get("role") == "system"
    ).strip()
    msgs = [
        {"role": m["role"], "content": str(m.get("content") or "")}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    payload = {
        "model": model,
        "max_tokens": 8000,
        "stream": True,
        "temperature": max(0.0, min(temp, 1.0)),
        "messages": msgs,
    }
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        base + "/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    text = ""
    try:
        resp = _OPENER.open(req, timeout=300)
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            ev_type = obj.get("type")
            if ev_type == "content_block_delta":
                delta = (obj.get("delta") or {}).get("text") or ""
                if delta:
                    text += delta
                    send({"t": "token", "v": delta})
            elif ev_type == "error":
                err = (obj.get("error") or {}).get("message") or "kesalahan tidak diketahui"
                send({"t": "error", "v": "Anthropic: %s" % err})
                return
            elif ev_type == "message_stop":
                break
        send({"t": "done", "v": text})
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 401:
            msg = "API key Anthropic ditolak (401) - periksa kembali key Anda."
        elif e.code == 404:
            msg = ("Model '%s' tidak ditemukan (404) - contoh ID benar: "
                   "claude-opus-5-5, claude-fable-5-1." % model)
        elif e.code == 429:
            msg = "Kuota/limit tercapai (429) - coba lagi nanti."
        else:
            msg = "Anthropic menolak permintaan (HTTP %s). %s" % (e.code, detail)
        send({"t": "error", "v": msg})
    except urllib.error.URLError as e:
        send({"t": "error", "v": "Tidak bisa terhubung ke %s - periksa koneksi internet. (%s)" % (base, getattr(e, "reason", ""))})
    except (TimeoutError, OSError):
        send({"t": "error", "v": "Koneksi ke Anthropic timeout atau terputus."})


def handle_chat_cloud(handler, body, messages, send):
    """Chat lewat API kompatibel OpenAI atau native Anthropic (Claude)."""
    base = str(body.get("api_base") or "").strip().rstrip("/")
    key = str(body.get("api_key") or "").strip()
    model = str(body.get("model") or "").strip()
    if not model:
        send({"t": "error", "v": "Nama model cloud belum diisi (Pengaturan > Cloud)."})
        return
    try:
        temp = float(body.get("temperature") or 0.7)
    except (TypeError, ValueError):
        temp = 0.7

    # API native Anthropic (Claude) - deteksi otomatis dari alamat
    if "anthropic" in base:
        _chat_anthropic(base, key, model, messages, temp, send)
        return

    payload = {"model": model, "messages": messages, "stream": True, "temperature": temp}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    text = ""
    try:
        resp = _OPENER.open(req, timeout=300)
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            try:
                delta = obj["choices"][0]["delta"].get("content") or ""
            except (KeyError, IndexError, TypeError, AttributeError):
                delta = ""
            if delta:
                text += delta
                send({"t": "token", "v": delta})
        send({"t": "done", "v": text})
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        if e.code == 401:
            msg = "API key ditolak (401) - periksa kembali key Anda."
        elif e.code == 404:
            msg = "Model '%s' tidak ditemukan di penyedia (404) - cek penulisan nama model." % model
        elif e.code == 429:
            msg = "Kuota/limit tercapai (429) - coba lagi nanti atau ganti model."
        else:
            msg = "Penyedia cloud menolak permintaan (HTTP %s). %s" % (e.code, detail)
        send({"t": "error", "v": msg})
    except urllib.error.URLError as e:
        send({"t": "error", "v": "Tidak bisa terhubung ke %s - periksa koneksi internet dan alamat URL. (%s)" % (base, getattr(e, "reason", ""))})
    except (TimeoutError, OSError):
        send({"t": "error", "v": "Koneksi ke penyedia cloud timeout atau terputus."})


def handle_chat(handler, body):
    """Loop utama agen: panggil Ollama, jalankan tools, ulangi, kirim event."""
    ollama_url = str(body.get("ollama_url") or DEFAULT_OLLAMA).strip()
    if not ollama_url.startswith(("http://", "https://")):
        raise ChatError("Alamat Ollama tidak valid (harus diawali http:// atau https://).")

    model = str(body.get("model") or "llama3.2")
    sysp = str(body.get("system_prompt") or DEFAULT_SYSTEM)
    kn = load_knowledge()
    if kn:
        sysp += "\n\n=== KONTEKS APLIKASI (dari PENGETAHUAN.md) ===\n" + kn

    messages = [{"role": "system", "content": sysp}]
    for m in body.get("messages") or []:
        if m.get("role") not in ("user", "assistant", "tool"):
            continue
        if not (m.get("content") or m.get("tool_calls")):
            continue
        item = {"role": m["role"], "content": str(m.get("content") or "")}
        if m.get("tool_calls"):
            item["tool_calls"] = m["tool_calls"]
        if m.get("tool_name"):
            item["tool_name"] = m["tool_name"]
        messages.append(item)

    use_tools = bool(body.get("tools"))
    try:
        temp = float(body.get("temperature"))
    except (TypeError, ValueError):
        temp = 0.7

    # Mode cloud: pakai API kompatibel OpenAI, tanpa tools
    if body.get("api_key") and body.get("api_base"):
        send = handler.send_event
        if use_tools:
            send({"t": "notice", "v": "Mode cloud: tools (buat file) tidak aktif."})
        handle_chat_cloud(handler, body, messages, send)
        return

    send = handler.send_event

    for _attempt in range(8):  # batas 8 putaran tool agar tidak loop selamanya
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temp, "num_ctx": 4096},
        }
        if use_tools:
            extra = [t for p in PLUGINS for t in p["tools"]]
            payload["tools"] = TOOLS + extra
        if body.get("keep_alive") is not None:
            payload["keep_alive"] = body.get("keep_alive")

        content = ""
        tool_calls = []
        gen = None
        try:
            gen = ollama_stream(ollama_url, payload)
            for chunk in gen:
                msg = chunk.get("message") or {}
                tok = msg.get("content") or ""
                if tok:
                    content += tok
                    send({"t": "token", "v": tok})
                for tc in msg.get("tool_calls") or []:
                    fn = (tc or {}).get("function") or {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    if fn.get("name"):
                        tool_calls.append({"name": fn["name"], "args": args})
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            if use_tools and e.code in (400, 404):
                # Kemungkinan model tidak mendukung tools -> coba chat biasa
                use_tools = False
                send(
                    {
                        "t": "notice",
                        "v": "Model ini tidak mendukung tools - beralih ke mode chat biasa.",
                    }
                )
                continue
            raise ChatError("Ollama menolak permintaan (HTTP %s). %s" % (e.code, detail))
        except urllib.error.URLError:
            raise ChatError(
                'Tidak bisa terhubung ke Ollama di %s. Pastikan aplikasi Ollama '
                'sedang berjalan (ikon unta di pojok layar), atau jalankan "ollama serve" '
                "di terminal." % ollama_url
            )
        except (TimeoutError, OSError) as e:
            if isinstance(e, (BrokenPipeError, ConnectionResetError)):
                raise
            raise ChatError(
                "Koneksi ke Ollama timeout atau terputus. Coba lagi, atau pakai model "
                "yang lebih kecil."
            )
        finally:
            if gen is not None:
                try:
                    gen.close()
                except Exception:
                    pass

        if tool_calls and use_tools:
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {"function": {"name": tc["name"], "arguments": tc["args"]}}
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                send({"t": "tool", "name": tc["name"], "args": tc["args"]})
                ok, result = run_tool(tc["name"], tc["args"])
                send({"t": "toolresult", "name": tc["name"], "ok": ok, "v": str(result)[:4000]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tc["name"],
                        "content": ("OK: " if ok else "ERROR: ") + str(result)[:8000],
                    }
                )
            continue  # minta model merespons hasil tool

        send({"t": "done", "v": content})
        return

    send({"t": "done", "v": content})


# ----------------------------------------------------------------------------
# HTTP server
# ----------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "KilatAI/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGINS)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Filename, X-Embed-Key, Authorization",
        )

    def _check_embed_key(self):
        # True jika permintaan boleh lanjut (lihat EMBED_KEY di atas).
        if not EMBED_KEY:
            return True
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True  # permintaan langsung / iframe sesama origin
        if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
            return True
        # Origin sendiri (halaman UI / iframe /embed milik server ini) diizinkan,
        # termasuk saat diakses lewat IP LAN atau nama domain.
        host = (self.headers.get("Host") or "").strip()
        if host and (origin == "http://" + host or origin == "https://" + host):
            return True
        return self.headers.get("X-Embed-Key") == EMBED_KEY

    def log_message(self, fmt, *args):
        try:
            sys.stderr.write("  %s\n" % (fmt % args))
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        if parsed.path == "/api/history":
            cid = q.get("id", [""])[0]
            if not cid:
                self._send_json({"error": "parameter id wajib"}, 400)
                return
            storage.delete_conversation(cid)
            storage.audit("chat.deleted", cid)
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Tidak ditemukan."}, 404)

    # ---- util ----
    def send_event(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self):
        data = UI_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, name, download=False):
        p = safe_path(name)
        if not p or not os.path.isfile(p):
            self._send_json({"error": "File tidak ditemukan: %s" % name}, 404)
            return
        try:
            with open(p, "rb") as fh:
                data = fh.read()
        except OSError as e:
            self._send_json({"error": "Gagal membaca file: %s" % e}, 500)
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header(
                "Content-Disposition",
                "attachment; filename*=UTF-8''" + quote(os.path.basename(p)),
            )
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        if path.startswith("/api/") and not self._check_embed_key():
            self._send_json({"error": "Ditolak: embed key salah atau tidak ada."}, 403)
            return

        if path == "/logo":
            try:
                with open(os.path.join(BASE_DIR, "logo.png"), "rb") as fh:
                    data = fh.read()
            except OSError:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        elif path == "/embed":
            data = EMBED_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        elif path == "/widget.js":
            data = WIDGET_JS.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        elif path == "/demo":
            p = os.path.join(BASE_DIR, "contoh-embed.html")
            try:
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError:
                self._send_json({"error": "contoh-embed.html tidak ditemukan."}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        elif path in ("/", "/index.html"):
            self._send_html()

        elif path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Connection", "close")
            self.end_headers()

        elif path == "/api/history":
            cid = q.get("id", [""])[0]
            if cid:
                self._send_json({"id": cid, "messages": storage.get_messages(cid)})
            else:
                self._send_json({"conversations": storage.list_conversations()})

        elif path == "/api/models":
            url = (q.get("url", [""])[0] or DEFAULT_OLLAMA).strip()
            if not url.startswith(("http://", "https://")):
                self._send_json({"models": [], "error": "Alamat Ollama tidak valid."})
                return
            ckey = "cache:models:" + url
            cached = storage.cache_get(ckey)
            if cached:
                try:
                    self._send_json(json.loads(cached))
                    return
                except ValueError:
                    pass
            try:
                req = urllib.request.Request(url.rstrip("/") + "/api/tags", method="GET")
                with _OPENER.open(req, timeout=5) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"))
                payload = {"models": data.get("models") or []}
                storage.cache_set(ckey, 15, json.dumps(payload, ensure_ascii=False))
                self._send_json(payload)
            except urllib.error.URLError:
                self._send_json(
                    {
                        "models": [],
                        "error": "Tidak bisa terhubung ke %s - pastikan Ollama sedang berjalan." % url,
                    }
                )
            except Exception as e:
                self._send_json({"models": [], "error": str(e)[:200]})

        elif path == "/api/files":
            cached = storage.cache_get("cache:files")
            if cached:
                try:
                    self._send_json(json.loads(cached))
                    return
                except ValueError:
                    pass
            payload = {"files": list_workspace()}
            storage.cache_set("cache:files", 3, json.dumps(payload, ensure_ascii=False))
            self._send_json(payload)

        elif path == "/api/file":
            name = q.get("name", [""])[0]
            dl = q.get("dl", [""])[0] == "1"
            self._serve_file(name, dl)

        else:
            self._send_json({"error": "Tidak ditemukan."}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/") and not self._check_embed_key():
            self._send_json({"error": "Ditolak: embed key salah atau tidak ada."}, 403)
            return

        if parsed.path == "/api/stt":
            # Terima blob audio, teruskan ke server Whisper (whisper.cpp) bila dikonfigurasi
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            audio = self.rfile.read(n) if n else b""
            if not WHISPER_URL:
                self._send_json(
                    {"error": "Server Whisper belum dikonfigurasi - jalankan app.py dengan "
                              "ARENA_WHISPER_URL=http://... (lihat PANDUAN.md bagian suara)."},
                    400,
                )
                return
            if not audio:
                self._send_json({"error": "Audio kosong."}, 400)
                return
            import uuid

            boundary = "----arena" + uuid.uuid4().hex
            head = (
                ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\njson\r\n").encode()
                + ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.webm\"\r\n"
                   "Content-Type: application/octet-stream\r\n\r\n").encode()
            )
            body = head + audio + ("\r\n--" + boundary + "--\r\n").encode()
            try:
                req = urllib.request.Request(
                    WHISPER_URL,
                    data=body,
                    method="POST",
                    headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                )
                with _OPENER.open(req, timeout=180) as r:
                    res = json.loads(r.read().decode("utf-8", "replace"))
                self._send_json({"text": str(res.get("text") or "").strip()})
            except urllib.error.HTTPError as e:
                self._send_json({"error": "Server Whisper menolak permintaan (HTTP %s)." % e.code}, 502)
            except (urllib.error.URLError, TimeoutError, OSError):
                self._send_json(
                    {"error": "Tidak bisa terhubung ke server Whisper di %s" % WHISPER_URL}, 502
                )
            return

        if parsed.path == "/api/history":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                self._send_json({"error": "Body JSON tidak valid."}, 400)
                return
            if not body.get("id"):
                self._send_json({"error": "id percakapan wajib."}, 400)
                return
            storage.save_conversation(body)
            storage.audit("chat.saved", "%s | %s" % (body.get("id"), str(body.get("title") or "")[:60]))
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/upload":
            name = unquote(self.headers.get("X-Filename") or "")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > 5 * 1024 * 1024:
                self._send_json({"error": "File terlalu besar (maksimal 5 MB)."}, 413)
                return
            data = self.rfile.read(n) if n else b""
            p = safe_path(name)
            if not name or not p:
                self._send_json({"error": "Nama file tidak valid."}, 400)
                return
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(data)
            except OSError as e:
                self._send_json({"error": "Gagal menyimpan: %s" % e}, 500)
                return
            storage.audit("file.uploaded", name)
            storage.cache_invalidate("cache:files")
            self._send_json({"ok": True, "name": name, "size": n})
            return

        if parsed.path != "/api/chat":
            self._send_json({"error": "Tidak ditemukan."}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n > 0 else b"{}"
            body = json.loads(raw.decode("utf-8", "replace") or "{}")
        except Exception:
            self._send_json({"error": "Body JSON tidak valid."}, 400)
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        try:
            handle_chat(self, body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # pengguna menekan tombol stop / menutup halaman
        except ChatError as e:
            try:
                self.send_event({"t": "error", "v": str(e)})
            except Exception:
                pass
        except Exception as e:
            try:
                self.send_event({"t": "error", "v": "Error tak terduga: %s" % e})
            except Exception:
                pass


# ----------------------------------------------------------------------------
# Antarmuka (HTML+CSS+JS) - disematkan agar tetap SATU file
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Halaman chat ringkas untuk di-embed (iframe) + script widget melayang
# ----------------------------------------------------------------------------
EMBED_HTML = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kilat AI</title>
<style>
:root{--bg:#0b0e14;--panel:#171c28;--border:rgba(255,255,255,.08);--text:#e7ebf3;
  --muted:#8b93a7;--accent:#6d7cff;--accent2:#9f6dff}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:var(--text);
  background:var(--bg);display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:9px;padding:10px 12px;background:#10141d;
  border-bottom:1px solid var(--border);flex-shrink:0}
.av{width:28px;height:28px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:14px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));flex-shrink:0}
header b{font-size:13.5px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
select{background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:8px;
  padding:5px 7px;font-size:11.5px;max-width:140px;font-family:inherit}
.msgs{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;gap:12px}
.hello{color:var(--muted);font-size:12.5px;line-height:1.6;text-align:center;margin:auto;padding:0 14px}
.msg.u{align-self:flex-end;max-width:85%;background:#1d2537;border:1px solid var(--border);
  border-radius:13px 13px 4px 13px;padding:8px 12px;font-size:13.5px;line-height:1.55;
  white-space:pre-wrap;word-wrap:break-word}
.msg.a{align-self:flex-start;max-width:95%;display:flex;gap:8px}
.msg.a .av{width:24px;height:24px;font-size:12px;border-radius:8px;margin-top:2px}
.msg.a .bd{min-width:0}
.md{font-size:13.5px;line-height:1.6;word-wrap:break-word}
.md p{margin:0 0 8px}.md p:last-child{margin:0}
.md h2,.md h3,.md h4{margin:10px 0 6px;font-size:14px}
.md ul,.md ol{margin:0 0 8px;padding-left:1.4em}
.md blockquote{margin:0 0 8px;padding:4px 10px;border-left:3px solid var(--accent);color:#c7cde0}
.md code{background:#1c2230;border:1px solid var(--border);padding:0 5px;border-radius:5px;font-size:12px;
  font-family:ui-monospace,Consolas,monospace}
.codeblock{margin:0 0 8px;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#0d1117}
.codeblock pre{margin:0;padding:10px;overflow-x:auto}
.codeblock code{background:none;border:0;padding:0;font-size:12px;font-family:ui-monospace,Consolas,monospace}
.err{color:#ffb3b3;font-size:12.5px;line-height:1.5}
.dots span{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--muted);
  margin-right:4px;animation:ab 1.2s infinite}
@keyframes ab{30%{transform:translateY(-4px);opacity:1}0%,60%,100%{opacity:.4}}
.cursor{display:inline-block;width:7px;height:13px;background:var(--accent);
  animation:cb 1s steps(2) infinite;vertical-align:-2px}
@keyframes cb{50%{opacity:0}}
.composer{display:flex;gap:8px;padding:10px 12px;background:#10141d;border-top:1px solid var(--border);flex-shrink:0}
textarea{flex:1;background:var(--panel);border:1px solid var(--border);border-radius:11px;color:var(--text);
  font-family:inherit;font-size:13.5px;padding:9px 11px;resize:none;outline:0;max-height:110px;line-height:1.5}
textarea:focus{border-color:var(--accent)}
.send{width:40px;height:40px;flex-shrink:0;border:0;border-radius:11px;font-size:14px;color:#fff;cursor:pointer;
  background:linear-gradient(135deg,var(--accent),var(--accent2))}
.send:disabled{opacity:.5;cursor:default}
.hint{font-size:10.5px;color:var(--muted);padding:0 12px 8px;background:#10141d;text-align:center}
::-webkit-scrollbar{width:8px}::-webkit-scrollbar-thumb{background:#2a3040;border-radius:8px}
</style>
</head>
<body>
<header>
  <img class="av" src="/logo" alt="">
  <b>Kilat AI</b>
  <select id="model" title="Model"><option value="">memuat&hellip;</option></select>
</header>
<div class="msgs" id="msgs">
  <div class="hello" id="hello">Halo! Saya asisten AI lokal.<br>Tanya apa saja &mdash; berjalan di komputer pemilik halaman ini.</div>
</div>
<div class="composer">
  <textarea id="in" rows="1" placeholder="Ketik pesan&hellip;"></textarea>
  <button class="send" id="send" title="Kirim">&#10148;</button>
</div>
<div class="hint">Powered by Kilat AI &mdash; AI lokal via Ollama</div>
<script>
'use strict';
function $(s){return document.querySelector(s);}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function md(src){
  var codes=[];
  src=String(src==null?'':src);
  src=src.replace(/```([\w+#-]*)[ \t]*\n?([\s\S]*?)(```|$)/g,function(m,lang,code){
    codes.push({lang:lang,code:code.replace(/\n$/,'')});return '\x00C'+(codes.length-1)+'\x00';});
  src=esc(src);
  function inline(s){
    s=s.replace(/`([^`\n]+)`/g,function(m,c){return '<code>'+c+'</code>';});
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    s=s.replace(/(^|[\s(>])\*([^*\n]+)\*/g,'$1<em>$2</em>');
    s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return s;
  }
  var lines=src.split('\n'),out=[],i=0,para=[];
  function flush(){if(para.length){out.push('<p>'+inline(para.join('<br>'))+'</p>');para=[];}}
  while(i<lines.length){
    var l=lines[i],m;
    if(m=l.match(/^\x00C(\d+)\x00\s*$/)){
      flush();var b=codes[+m[1]];
      out.push('<div class="codeblock"><pre><code>'+esc(b.code)+'</code></pre></div>');
      i++;continue;}
    if(m=l.match(/^(#{1,6})\s+(.*)$/)){
      flush();var h=Math.min(m[1].length+2,5);
      out.push('<h'+h+'>'+inline(m[2])+'</h'+h+'>');i++;continue;}
    if(/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l)){flush();out.push('<hr>');i++;continue;}
    if(/^&gt;/.test(l)){
      flush();var q=[];
      while(i<lines.length&&/^&gt;/.test(lines[i])){q.push(lines[i].replace(/^&gt;\s?/,''));i++;}
      out.push('<blockquote>'+inline(q.join('<br>'))+'</blockquote>');continue;}
    if(/^\s*[-*+]\s+/.test(l)){
      flush();var it=[];
      while(i<lines.length&&/^\s*[-*+]\s+/.test(lines[i])){it.push('<li>'+inline(lines[i].replace(/^\s*[-*+]\s+/,''))+'</li>');i++;}
      out.push('<ul>'+it.join('')+'</ul>');continue;}
    if(/^\s*\d+[.)]\s+/.test(l)){
      flush();var it2=[];
      while(i<lines.length&&/^\s*\d+[.)]\s+/.test(lines[i])){it2.push('<li>'+inline(lines[i].replace(/^\s*\d+[.)]\s+/,''))+'</li>');i++;}
      out.push('<ol>'+it2.join('')+'</ol>');continue;}
    if(l.trim()===''){flush();i++;continue;}
    para.push(l);i++;
  }
  flush();
  return out.join('\n');
}
var msgs=$('#msgs'),inEl=$('#in'),btn=$('#send'),sel=$('#model');
var KEY='';
try{KEY=new URLSearchParams(location.search).get('key')||'';}catch(e){}
var APIH=KEY?{'X-Embed-Key':KEY}:{};
function scroll(){msgs.scrollTop=msgs.scrollHeight;}
function loadModels(){
  fetch('/api/models',{headers:APIH}).then(function(r){return r.json();}).then(function(d){
    var ms=d.models||[];
    sel.innerHTML=ms.length?ms.map(function(m){
      return '<option value="'+esc(m.name)+'">'+esc(m.name)+'</option>';}).join('')
      :'<option value="">- tidak ada model -</option>';
    if(ms.length)$('#hello').innerHTML='Halo! Saya asisten AI lokal.<br>Tanya apa saja.';
  }).catch(function(){sel.innerHTML='<option value="">- server tidak aktif -</option>';});
}
var hist=[],streaming=false,ctrl=null;
function addUser(t){var d=document.createElement('div');d.className='msg u';d.textContent=t;msgs.appendChild(d);scroll();}
function addAI(){
  var d=document.createElement('div');d.className='msg a';
  d.innerHTML='<span class="av">&#9889;</span><div class="bd">'+
    '<div class="dots"><span></span><span></span><span></span></div></div>';
  msgs.appendChild(d);scroll();return d.querySelector('.bd');
}
function send(){
  var t=inEl.value.trim();
  if(!t||streaming)return;
  var model=sel.value;
  if(!model){sel.focus();return;}
  inEl.value='';inEl.style.height='auto';
  $('#hello').style.display='none';
  hist.push({role:'user',content:t});addUser(t);
  var body=addAI(),text='';
  streaming=true;btn.disabled=true;ctrl=new AbortController();
  fetch('/api/chat',{method:'POST',headers:Object.assign({'Content-Type':'application/json'},APIH),signal:ctrl.signal,
    body:JSON.stringify({model:model,messages:hist.slice(),tools:false})})
  .then(function(res){
    if(!res.ok)throw new Error('Server error '+res.status);
    var reader=res.body.getReader(),dec=new TextDecoder(),buf='';
    function pump(){return reader.read().then(function(r){
      if(r.done)return;
      buf+=dec.decode(r.value,{stream:true});
      var i;
      while((i=buf.indexOf('\n'))>=0){
        var line=buf.slice(0,i).trim();buf=buf.slice(i+1);
        if(!line)continue;
        var ev;try{ev=JSON.parse(line);}catch(e){continue;}
        if(ev.t==='token'){
          text+=ev.v;
          body.innerHTML='<div class="md">'+md(text)+'<span class="cursor"></span></div>';scroll();
        }else if(ev.t==='error'){
          body.innerHTML='<div class="md">'+md(text)+'</div>'+
            '<div class="err">&#9888;&#65039; '+esc(ev.v)+'</div>';scroll();
        }
      }
      return pump();
    });}
    return pump();
  }).catch(function(e){
    if(e&&e.name!=='AbortError'){
      body.innerHTML='<div class="err">&#9888;&#65039; '+esc(e.message||'Koneksi gagal')+'</div>';
    }
  }).then(function(){
    streaming=false;btn.disabled=false;
    if(text){hist.push({role:'assistant',content:text});
      body.innerHTML='<div class="md">'+md(text)+'</div>';}
    scroll();
  });
}
btn.addEventListener('click',send);
inEl.addEventListener('keydown',function(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}
});
inEl.addEventListener('input',function(){
  inEl.style.height='auto';inEl.style.height=Math.min(inEl.scrollHeight,110)+'px';
});
loadModels();
</script>
</body>
</html>
"""

WIDGET_JS = r"""/* Kilat AI - widget chat melayang
   Pakai di website Anda: <script src="http://ALAMAT-SERVER:8080/widget.js" defer></script> */
(function () {
  'use strict';
  if (window.__arenaWidgetLoaded) return;
  window.__arenaWidgetLoaded = true;
  var script = document.currentScript;
  var base = 'http://localhost:8080';
  try {
    if (script && script.src && /^https?:/i.test(script.src)) {
      base = new URL('.', script.src).href.replace(/\/$/, '');
    }
  } catch (e) {}
  var side = script && script.getAttribute('data-side') === 'left' ? 'left' : 'right';
  var key = script ? (script.getAttribute('data-key') || '') : '';

  function init() {
    var css = document.createElement('style');
    css.textContent = [
      '.arena-w-bubble{position:fixed;bottom:20px;' + side + ':20px;width:56px;height:56px;border-radius:50%;',
      'border:0;cursor:pointer;z-index:2147483000;font-size:26px;color:#fff;font-family:inherit;',
      'background:linear-gradient(135deg,#6d7cff,#9f6dff);box-shadow:0 6px 24px rgba(0,0,0,.35);',
      'display:flex;align-items:center;justify-content:center;transition:transform .15s}',
      '.arena-w-bubble:hover{transform:scale(1.08)}',
      '.arena-w-frame{position:fixed;bottom:88px;' + side + ':20px;width:360px;max-width:calc(100vw - 32px);',
      'height:520px;max-height:calc(100vh - 120px);border:1px solid rgba(0,0,0,.25);border-radius:16px;',
      'background:#0b0e14;z-index:2147483000;box-shadow:0 16px 48px rgba(0,0,0,.4);display:none;overflow:hidden}'
    ].join('');
    document.head.appendChild(css);

    var frame = document.createElement('iframe');
    frame.className = 'arena-w-frame';
    frame.src = base + '/embed' + (key ? '?key=' + encodeURIComponent(key) : '');
    frame.setAttribute('title', 'Chat Kilat AI');
    document.body.appendChild(frame);

    var btn = document.createElement('button');
    btn.className = 'arena-w-bubble';
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Buka chat Kilat AI');
    btn.innerHTML = '&#9889;';
    document.body.appendChild(btn);
    btn.addEventListener('click', function () {
      var show = frame.style.display !== 'block';
      frame.style.display = show ? 'block' : 'none';
      btn.innerHTML = show ? '&#10005;' : '&#9889;';
    });
  }
  if (document.body) init();
  else document.addEventListener('DOMContentLoaded', init);
})();
"""

UI_HTML = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kilat AI - AI di komputermu</title>
<link rel="icon" type="image/png" href="/logo">
<style>
:root{
  --bg:#0b0e14; --panel:#10141d; --panel2:#171c28; --border:rgba(255,255,255,.08);
  --text:#e7ebf3; --muted:#8b93a7; --accent:#6d7cff; --accent2:#9f6dff;
  --user:#1d2537; --ok:#3ecf8e; --err:#ff6b6b; color-scheme:dark;
}
[hidden]{display:none!important}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  color:var(--text);background:radial-gradient(1100px 520px at 50% -12%,rgba(109,124,255,.13),transparent),var(--bg);}
.app{display:flex;height:100vh;overflow:hidden}
button{font-family:inherit;cursor:pointer}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:#2a3040;border-radius:9px}
::-webkit-scrollbar-track{background:transparent}

/* ---------- sidebar ---------- */
#sidebar{width:274px;flex-shrink:0;background:var(--panel);border-right:1px solid var(--border);
  display:flex;flex-direction:column;transition:transform .25s ease}
.side-head{display:flex;align-items:center;justify-content:space-between;padding:14px 12px 10px 16px}
.logo{display:flex;gap:10px;align-items:center}
.logo-badge{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;
  font-size:19px;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 4px 18px rgba(109,124,255,.35)}
.logo-name{font-weight:700;font-size:15.5px;letter-spacing:.2px}
.logo-sub{font-size:11.5px;color:var(--muted)}
.new-chat{margin:6px 14px 10px;padding:10px 12px;border-radius:11px;border:1px dashed rgba(255,255,255,.18);
  background:transparent;color:var(--text);font-size:13.5px;font-weight:600}
.new-chat:hover{border-color:var(--accent);background:rgba(109,124,255,.09)}
.chat-list{flex:1;overflow-y:auto;padding:2px 8px}
.chat-item{position:relative;padding:9px 30px 9px 12px;border-radius:10px;cursor:pointer;margin-bottom:2px}
.chat-item:hover{background:var(--panel2)}
.chat-item.active{background:var(--panel2);box-shadow:inset 2px 0 0 var(--accent)}
.ci-title{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ci-time{font-size:10.5px;color:var(--muted);margin-top:2px}
.ci-del{position:absolute;right:6px;top:50%;transform:translateY(-50%);border:0;background:transparent;
  color:var(--muted);font-size:12px;border-radius:7px;padding:4px 5px;opacity:0}
.chat-item:hover .ci-del{opacity:1}
.ci-del:hover{color:var(--err);background:rgba(255,107,107,.12)}
.side-foot{padding:12px 16px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);line-height:1.6}
.side-foot b{color:#aab3c8}

/* ---------- main ---------- */
main{flex:1;display:flex;flex-direction:column;min-width:0}
header{display:flex;align-items:center;gap:8px;row-gap:6px;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid var(--border);
  background:rgba(16,20,29,.7);backdrop-filter:blur(6px)}
.brand-mob{display:none;font-weight:700}
#openSide{display:none}
.spacer{flex:1}
select#modelSel{background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:10px;
  padding:8px 10px;font-size:13px;max-width:280px}
.icon-btn{background:transparent;border:1px solid var(--border);color:var(--text);border-radius:10px;
  width:36px;height:36px;font-size:15px;display:inline-flex;align-items:center;justify-content:center}
.icon-btn:hover{border-color:var(--accent);background:rgba(109,124,255,.1)}
.chip{background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:999px;
  padding:7px 13px;font-size:12.5px}
.chip:hover{border-color:var(--accent)}
.chip.off{opacity:.45}
.badge{background:linear-gradient(135deg,#f7b733,#fc4a1a);color:#1a1200;font-size:10px;font-weight:800;
  padding:3px 8px;border-radius:999px;letter-spacing:.6px}
.banner{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:10px 14px 0;padding:10px 14px;
  border-radius:11px;background:rgba(255,176,32,.08);border:1px solid rgba(255,176,32,.35);font-size:13px}
.banner code{background:#241d0c;padding:1px 6px;border-radius:6px}
.mini-btn{background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:9px;
  padding:6px 12px;font-size:12.5px}
.mini-btn:hover{border-color:var(--accent)}

/* ---------- messages ---------- */
.messages{flex:1;overflow-y:auto;padding:22px 20px 6px;display:flex;flex-direction:column;gap:20px}
.msg-col{width:100%;max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
.msg.user{display:flex;justify-content:flex-end}
.msg.user .bubble{background:var(--user);border:1px solid var(--border);padding:10px 15px;border-radius:16px 16px 4px 16px;
  max-width:78%;white-space:pre-wrap;word-wrap:break-word;font-size:14.5px;line-height:1.6}
.msg.ai{display:flex;gap:12px}
.avatar{width:31px;height:31px;flex-shrink:0;border-radius:10px;display:flex;align-items:center;justify-content:center;
  font-size:15px;background:linear-gradient(135deg,var(--accent),var(--accent2))}
.ai-main{flex:1;min-width:0}
.ai-actions{display:flex;align-items:center;gap:10px;margin-top:8px;opacity:.85}
.linkbtn{background:transparent;border:0;color:var(--muted);font-size:11.5px;padding:2px 4px;border-radius:6px}
.linkbtn:hover{color:var(--text);background:var(--panel2)}
.aimeta{font-size:11px;color:var(--muted)}
.md{font-size:14.5px;line-height:1.7;word-wrap:break-word}
.md p{margin:0 0 10px}
.md p:last-child{margin-bottom:0}
.md h2,.md h3,.md h4,.md h5{margin:16px 0 8px;line-height:1.35}
.md ul,.md ol{margin:0 0 10px;padding-left:1.5em}
.md li{margin:3px 0}
.md blockquote{margin:0 0 10px;padding:6px 14px;border-left:3px solid var(--accent);background:rgba(109,124,255,.07);
  border-radius:0 9px 9px 0;color:#c7cde0}
.md code{background:#1c2230;border:1px solid var(--border);padding:1px 6px;border-radius:6px;font-size:12.8px;
  font-family:ui-monospace,'Cascadia Code',Consolas,Menlo,monospace}
.md a{color:#9fb1ff}
.md hr{border:0;border-top:1px solid var(--border);margin:14px 0}
.tablewrap{overflow-x:auto;margin:0 0 10px}
.md table{border-collapse:collapse;font-size:13px}
.md th,.md td{border:1px solid var(--border);padding:6px 11px;text-align:left}
.md th{background:var(--panel2)}
.codeblock{margin:0 0 10px;border:1px solid var(--border);border-radius:11px;overflow:hidden;background:#0d1117}
.codehead{display:flex;justify-content:space-between;align-items:center;padding:6px 7px 6px 13px;
  background:#131a26;border-bottom:1px solid var(--border);font-size:11px;color:var(--muted)}
.copycode{background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:7px;
  padding:3px 10px;font-size:11px}
.copycode:hover{color:var(--text);border-color:var(--accent)}
.codeblock pre{margin:0;padding:13px;overflow-x:auto}
.codeblock code{background:transparent;border:0;padding:0;font-size:13px;font-family:ui-monospace,'Cascadia Code',Consolas,Menlo,monospace;line-height:1.55}
.cursor{display:inline-block;width:8px;height:15px;background:var(--accent);margin-left:2px;
  animation:blink 1s steps(2) infinite;vertical-align:-2px}
@keyframes blink{50%{opacity:0}}
.dots{display:inline-flex;gap:5px;padding:6px 0}
.dots span{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:bob 1.2s infinite}
.dots span:nth-child(2){animation-delay:.18s}.dots span:nth-child(3){animation-delay:.36s}
@keyframes bob{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-5px);opacity:1}}
.errnote{margin-top:8px;background:rgba(255,107,107,.09);border:1px solid rgba(255,107,107,.35);color:#ffb3b3;
  padding:9px 13px;border-radius:10px;font-size:13px}

/* tool events */
.evs{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
.ev{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:var(--panel2);border:1px solid var(--border);
  border-radius:10px;padding:7px 11px;font-size:12.5px;position:relative}
.ev-name{font-weight:700;font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#b9c3da}
.ev code{background:#1c2230;padding:1px 6px;border-radius:6px;font-size:11.5px}
.ev-det{width:100%;display:block;background:#0d1117;border:1px solid var(--border);border-radius:9px;padding:11px;
  margin:4px 0 0;font-size:11.5px;white-space:pre-wrap;max-height:260px;overflow-y:auto;font-family:ui-monospace,Consolas,monospace;color:#aeb6c9}
.spin{display:inline-block;animation:rot 1s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}

/* ---------- arena ---------- */
.verdict{display:flex;flex-direction:column;gap:3px;background:linear-gradient(135deg,rgba(247,183,51,.12),rgba(252,74,26,.08));
  border:1px solid rgba(247,183,51,.4);border-radius:12px;padding:10px 13px;margin-bottom:12px;font-size:13px;line-height:1.55}
.verdict b{color:#ffd98a}
.arena-card{border:1px solid var(--border);border-radius:13px;margin-bottom:10px;overflow:hidden;background:rgba(13,17,23,.45)}
.arena-card.win{border-color:rgba(62,207,142,.55);box-shadow:0 0 0 1px rgba(62,207,142,.25)}
.ac-head{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#131a26;border-bottom:1px solid var(--border);
  font-size:12.5px;cursor:pointer}
.ac-name{font-weight:700;font-family:ui-monospace,Consolas,monospace;font-size:12px;flex:1;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.ac-body{padding:12px 14px}
.ac-body .md{font-size:13.5px}
.ac-status{font-size:10.5px;color:var(--muted)}
.pickbtn{background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:3px 9px;font-size:11px}
.pickbtn:hover{border-color:var(--ok);color:var(--ok)}
.wintag{background:rgba(62,207,142,.15);color:#7ee2b8;border:1px solid rgba(62,207,142,.4);font-size:10px;
  font-weight:800;border-radius:999px;padding:2px 8px}
.model-check{display:flex;align-items:center;gap:10px;padding:9px 11px;border:1px solid var(--border);border-radius:10px;
  margin-bottom:7px;cursor:pointer;font-size:13px}
.model-check:hover{border-color:var(--accent)}
.model-check input{accent-color:var(--accent);width:16px;height:16px}
.model-check .mc-name{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;flex:1}
.model-check .mc-size{font-size:10.5px;color:var(--muted)}

/* ---------- empty state ---------- */
.empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;
  text-align:center;overflow-y:auto}
.empty-badge{width:66px;height:66px;border-radius:19px;display:flex;align-items:center;justify-content:center;
  font-size:33px;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 10px 40px rgba(109,124,255,.4);margin-bottom:18px}
.empty h1{font-size:23px;margin:0 0 8px}
.empty p{color:var(--muted);font-size:14px;max-width:440px;margin:0 0 22px;line-height:1.6}
.chips{display:flex;flex-wrap:wrap;gap:9px;justify-content:center;max-width:560px}
.chips button{background:var(--panel2);border:1px solid var(--border);color:var(--text);border-radius:999px;
  padding:9px 15px;font-size:13px}
.chips button:hover{border-color:var(--accent);background:rgba(109,124,255,.1)}

/* ---------- composer ---------- */
.composer{padding:8px 20px 14px}
.composer-inner{max-width:820px;margin:0 auto}
.composer-box{display:flex;align-items:flex-end;gap:9px;background:var(--panel2);border:1px solid var(--border);
  border-radius:17px;padding:10px 10px 10px 16px;transition:border-color .15s}
.composer-box:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(109,124,255,.15)}
textarea#input{flex:1;background:transparent;border:0;outline:0;resize:none;color:var(--text);
  font-size:14.5px;font-family:inherit;line-height:1.55;max-height:200px;padding:6px 0}
textarea#input::placeholder{color:#5d6578}
.send{width:38px;height:38px;flex-shrink:0;border:0;border-radius:12px;font-size:15px;color:#fff;
  background:linear-gradient(135deg,var(--accent),var(--accent2))}
.send:hover{filter:brightness(1.12)}
.send.stop{background:linear-gradient(135deg,#ff6b6b,#fc4a1a)}
.send.mic{background:var(--panel2);border:1px solid var(--border);color:var(--text)}
.send.mic.rec{background:linear-gradient(135deg,#ff6b6b,#fc4a1a);color:#fff;animation:micpulse 1.1s infinite}
@keyframes micpulse{50%{box-shadow:0 0 0 7px rgba(255,107,107,.25)}}
.composer-hint{text-align:center;font-size:11px;color:var(--muted);margin-top:8px}

/* ---------- files panel ---------- */
.files{width:330px;flex-shrink:0;background:var(--panel);border-left:1px solid var(--border);
  display:flex;flex-direction:column}
.files-head{display:flex;align-items:center;justify-content:space-between;padding:12px 10px 12px 16px;
  border-bottom:1px solid var(--border)}
.files-head>div{display:flex;gap:6px}
.files-note{font-size:11.5px;color:var(--muted);padding:10px 16px;border-bottom:1px solid var(--border);line-height:1.5}
.files-note code{background:#1c2230;padding:1px 5px;border-radius:5px}
.file-list{flex:1;overflow-y:auto;padding:8px}
.file{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:10px;cursor:pointer;font-size:13px}
.file:hover{background:var(--panel2)}
.fname{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fsize{font-size:10.5px;color:var(--muted)}
.files-empty{padding:18px 14px;font-size:12.5px;color:var(--muted);text-align:center;line-height:1.6}

/* ---------- modal & toast ---------- */
.overlay{position:fixed;inset:0;background:rgba(5,8,14,.62);display:flex;align-items:center;justify-content:center;
  z-index:90;padding:18px}
.modal{width:min(560px,94vw);max-height:88vh;overflow-y:auto;background:var(--panel2);border:1px solid var(--border);
  border-radius:17px;padding:20px;box-shadow:0 24px 70px rgba(0,0,0,.5)}
.modal.wide{width:min(760px,94vw)}
.modal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;font-size:16px}
.modal label{display:block;font-size:12.5px;color:var(--muted);margin:13px 0 5px;font-weight:600}
.modal input[type=text],.modal input[type=password],.modal textarea{width:100%;background:var(--panel);border:1px solid var(--border);
  color:var(--text);border-radius:10px;padding:9px 12px;font-size:13.5px;font-family:inherit;outline:0}
.modal input[type=text]:focus,.modal input[type=password]:focus,.modal textarea:focus{border-color:var(--accent)}
.modal textarea{resize:vertical;line-height:1.55}
input[type=range]{width:100%;accent-color:var(--accent)}
.check{display:flex!important;align-items:center;gap:9px;font-size:13px!important;color:var(--text)!important;cursor:pointer}
.check input{accent-color:var(--accent);width:16px;height:16px}
.modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}
.primary{background:linear-gradient(135deg,var(--accent),var(--accent2));border:0;color:#fff;
  border-radius:10px;padding:9px 18px;font-size:13.5px;font-weight:600}
a.primary{text-decoration:none;display:inline-block}
#viewBody{background:#0d1117;border:1px solid var(--border);border-radius:11px;padding:14px;max-height:56vh;
  overflow:auto;font-size:12.5px;white-space:pre-wrap;line-height:1.55;font-family:ui-monospace,Consolas,monospace;margin:0}
.toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:#232b3d;border:1px solid var(--border);
  color:var(--text);padding:11px 19px;border-radius:999px;font-size:13px;z-index:120;box-shadow:0 10px 34px rgba(0,0,0,.5);
  max-width:90vw;text-align:center}

/* ---------- tema terang ---------- */
body.light{--bg:#eef1f7;--panel:#ffffff;--panel2:#f1f4fa;--border:rgba(20,30,60,.13);
  --text:#1b2233;--muted:#5c6780;--accent:#5a67e8;--accent2:#8a5cf0;--user:#e4eafc;
  background:radial-gradient(1100px 520px at 50% -12%,rgba(90,103,232,.10),transparent),var(--bg)}
body.light .md code{background:#e8ecf5;border-color:rgba(20,30,60,.13)}
body.light .codeblock{background:#f7f9fc}
body.light .codehead{background:#eceff7;border-color:rgba(20,30,60,.13)}
body.light .ev code{background:#e8ecf5}
body.light .ev-det{background:#f7f9fc;color:#3c4761;border-color:rgba(20,30,60,.13)}
body.light .errnote{background:rgba(220,60,60,.07);border-color:rgba(220,60,60,.3);color:#b02a2a}
body.light ::-webkit-scrollbar-thumb{background:#c3cbdd}

/* ---------- mobile ---------- */
@media (max-width:920px){
  #sidebar{position:fixed;top:0;left:0;bottom:0;z-index:80;transform:translateX(-102%);
    box-shadow:14px 0 40px rgba(0,0,0,.45)}
  body.side-open #sidebar{transform:translateX(0)}
  #openSide{display:inline-flex}
  .brand-mob{display:block}
  .files{position:fixed;top:0;right:0;bottom:0;z-index:85;width:min(330px,92vw);box-shadow:-14px 0 40px rgba(0,0,0,.45)}
  .side-head .icon-btn{display:inline-flex}
  #closeSide{display:inline-flex}
  select#modelSel{max-width:150px}
}
@media (min-width:921px){#closeSide{display:none}}
</style>
</head>
<body>
<div class="app">

  <aside id="sidebar">
    <div class="side-head">
      <div class="logo">
        <img src="/logo" alt="Kilat AI" style="width:38px;height:38px;border-radius:11px;object-fit:cover;box-shadow:0 4px 18px rgba(109,124,255,.35)">
        <div>
          <div class="logo-name">Kilat AI</div>
          <div class="logo-sub">AI di komputermu sendiri</div>
        </div>
      </div>
      <button class="icon-btn" id="closeSide" title="Tutup menu">&#10005;</button>
    </div>
    <button class="new-chat" id="newChatBtn">＋ Obrolan Baru</button>
    <div class="chat-list" id="chatList"></div>
    <div class="side-foot">
      <span id="footMode"><b>100% lokal &amp; privat</b> &mdash; percakapan tidak keluar dari komputer Anda.</span><br>
      <span id="footStat"></span>
    </div>
  </aside>

  <main>
    <header>
      <button class="icon-btn" id="openSide" title="Menu">&#9776;</button>
      <div class="brand-mob">&#9889; Kilat AI</div>
      <select id="modelSel" title="Pilih model AI"><option value="">memuat&hellip;</option></select>
      <button class="icon-btn" id="refreshModels" title="Muat ulang daftar model">&#10227;</button>
      <span class="badge" id="demoBadge" hidden>MODE&nbsp;DEMO</span>
      <div class="spacer"></div>
      <button class="chip" id="toolsBtn" title="Agen boleh membuat &amp; membaca file di workspace">&#128295; Tools: ON</button>
      <button class="chip" id="arenaBtn" title="Mode Arena - tanya beberapa model sekaligus, juri memilih jawaban terbaik">&#127951;&#65039; Arena: OFF</button>
      <button class="chip" id="filesBtn">&#128193; Workspace</button>
      <button class="icon-btn" id="settingsBtn" title="Pengaturan">&#9881;&#65039;</button>
      <button class="icon-btn" id="themeBtn" title="Tema terang/gelap">&#127769;</button>
    </header>

    <div class="banner" id="connBanner" hidden>
      <span id="connText" style="flex:1"></span>
      <button class="mini-btn" id="reloadModels">Muat ulang</button>
    </div>

    <div class="messages" id="messages"><div class="msg-col" id="msgCol"></div></div>

    <div class="empty" id="empty" hidden>
      <div class="empty-badge">&#9889;</div>
      <h1>Halo! Saya AI lokalmu &#128075;</h1>
      <p>Tanya apa saja &mdash; atau minta saya membuat file di workspace. Semuanya berjalan
         di komputer Anda sendiri, tanpa internet.</p>
      <div class="chips" id="chips">
        <button data-q="Buatkan file catatan.txt berisi rencana harian saya yang rapi">&#128196; Buat file catatan.txt</button>
        <button data-q="Jelaskan apa itu Ollama dan cara kerjanya, singkat saja">&#129504; Apa itu Ollama?</button>
        <button data-q="Tulis puisi singkat tentang hujan di Bogor lalu simpan ke file puisi.txt">&#9997;&#65039; Puisi hujan di Bogor</button>
        <button data-q="Lihat daftar file di workspace saya">&#128194; Lihat file workspace</button>
      </div>
    </div>

    <div class="composer">
      <div class="composer-inner">
        <div class="composer-box">
          <textarea id="input" rows="1" placeholder="Ketik pesan&hellip;  (Enter kirim &bull; Shift+Enter baris baru)"></textarea>
          <button class="send mic" id="micBtn" title="Bicara (input suara)">&#127908;</button>
          <button class="send" id="sendBtn" title="Kirim">&#10148;</button>
        </div>
        <div class="composer-hint">Jawaban dihasilkan model lokal lewat Ollama &mdash; bisa saja keliru, tetap periksa hal penting.</div>
      </div>
    </div>
  </main>

  <aside class="files" id="filesPanel" hidden>
    <div class="files-head">
      <b>&#128193; Workspace</b>
      <div>
        <button class="icon-btn" id="uploadBtn" title="Upload file ke workspace (maks 5 MB)">&#128229;</button>
        <button class="icon-btn" id="refreshFilesBtn" title="Muat ulang">&#10227;</button>
        <button class="icon-btn" id="closeFilesBtn" title="Tutup">&#10005;</button>
      </div>
    </div>
    <div class="files-note">File yang dibuat AI tersimpan di folder <code>workspace/</code> di samping <code>app.py</code>.</div>
    <div class="file-list" id="fileList"><div class="files-empty">Belum ada file.<br>Coba minta AI: &ldquo;buatkan file catatan.txt&rdquo;</div></div>
  </aside>
</div>

<input type="file" id="fileInput" multiple hidden>

<!-- Pengaturan -->
<div class="overlay" id="settingsModal" hidden>
  <div class="modal">
    <div class="modal-head"><b>&#9881;&#65039; Pengaturan</b>
      <button class="icon-btn" data-close>&#10005;</button></div>
    <label>Alamat server Ollama</label>
    <input type="text" id="setUrl" placeholder="http://localhost:11434">
    <label>System prompt (kepribadian &amp; instruksi AI)</label>
    <textarea id="setSys" rows="6"></textarea>
    <label>Temperature: <span id="tempVal">0.7</span> <span style="font-weight:400">(kecil=fokus, besar=kreatif)</span></label>
    <input type="range" id="setTemp" min="0" max="1.5" step="0.1" value="0.7">
    <label class="check"><input type="checkbox" id="setTools" checked>
      Aktifkan mode agen &mdash; AI boleh membuat &amp; membaca file di folder workspace</label>
    <label class="check" style="margin-top:13px"><input type="checkbox" id="setCloud">
      &#9729;&#65039; Mode Cloud &mdash; pakai API key (opsional, butuh internet)</label>
    <div id="cloudBox" style="display:none">
      <label>Alamat API (base URL)</label>
      <input type="text" id="setCBase" placeholder="https://openrouter.ai/v1">
      <label>API key</label>
      <input type="password" id="setCKey" placeholder="sk-...">
      <label>Nama model</label>
      <input type="text" id="setCModel" placeholder="mis. openai/gpt-4o-mini">
      <p style="font-size:11.5px;color:var(--muted);line-height:1.55;margin:10px 0 0">
        &#9888;&#65039; Saat cloud aktif, percakapan keluar dari komputer Anda ke penyedia API.
        Tools &amp; Mode Arena nonaktif. Contoh: OpenRouter (<code>https://openrouter.ai/v1</code>),
        Anthropic Claude (<code>https://api.anthropic.com</code> - model <code>claude-opus-5-5</code> /
        <code>claude-fable-5-1</code>, dideteksi otomatis), OpenAI, Groq,
        atau LM Studio lokal (<code>http://localhost:1234/v1</code>).</p>
    </div>
    <label>Server Whisper untuk input suara offline (opsional)</label>
    <input type="text" id="setWhisper" placeholder="mis. http://127.0.0.1:8081/inference">
    <p style="font-size:11.5px;color:var(--muted);line-height:1.55;margin:8px 0 0">
      Kosongkan untuk memakai speech recognition bawaan browser (Chrome/Edge - butuh internet).
      Isi alamat server whisper.cpp untuk input suara 100% offline.</p>
    <div class="modal-actions">
      <button class="mini-btn" data-close>Batal</button>
      <button class="primary" id="saveSettingsBtn">Simpan</button>
    </div>
  </div>
</div>

<!-- Pratinjau file -->
<div class="overlay" id="viewerModal" hidden>
  <div class="modal wide">
    <div class="modal-head"><b id="viewName">file</b>
      <button class="icon-btn" data-close>&#10005;</button></div>
    <pre id="viewBody"></pre>
    <div class="modal-actions">
      <button class="mini-btn" id="viewToggle" type="button" style="display:none">&#128196; Lihat mentah</button>
      <button class="mini-btn" data-close>Tutup</button>
      <a class="primary" id="viewDl" href="#" download>&#11015;&#65039; Unduh</a>
    </div>
  </div>
</div>

<!-- Mode Arena -->
<div class="overlay" id="arenaModal" hidden>
  <div class="modal">
    <div class="modal-head"><b>&#127951;&#65039; Mode Arena</b>
      <button class="icon-btn" data-close>&#10005;</button></div>
    <p style="font-size:13px;color:var(--muted);line-height:1.6;margin:0 0 12px">
      Satu pertanyaan dijawab <b>beberapa model sekaligus</b>, lalu <b>model juri</b> menilai dan
      memilih jawaban terbaik &#127942;. Model dijalankan bergantian agar RAM aman.
      Saat Mode Arena aktif, tools (buat file) nonaktif.</p>
    <label class="check"><input type="checkbox" id="arEnable"> Aktifkan Mode Arena</label>
    <label>Model peserta (centang 2&ndash;4)</label>
    <div style="display:flex;align-items:center;gap:9px;margin:4px 0 8px;flex-wrap:wrap">
      <button class="mini-btn" id="arRecBtn" type="button">&#11088; Pakai rekomendasi</button>
      <span style="font-size:11px;color:var(--muted)">centang default = rekomendasi terbaik dari model yang terpasang</span>
    </div>
    <div id="arModels"></div>
    <label>Model juri (menilai &amp; memilih jawaban terbaik)</label>
    <select id="arJudge" style="width:100%;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:10px;padding:9px 12px;font-size:13.5px"></select>
    <div class="modal-actions">
      <button class="mini-btn" data-close>Batal</button>
      <button class="primary" id="saveArenaBtn">Simpan</button>
    </div>
  </div>
</div>

<div class="toast" id="toast" hidden></div>

<script>
'use strict';
/* ================= util ================= */
var $=function(s){return document.querySelector(s);};
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function loadLS(k,d){try{var v=localStorage.getItem(k);return v?JSON.parse(v):d;}catch(e){return d;}}
function saveLS(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2,7);}
function fmtSize(n){if(n>=1073741824)return (n/1073741824).toFixed(1)+' GB';if(n>=1048576)return (n/1048576).toFixed(1)+' MB';if(n>=1024)return (n/1024).toFixed(1)+' KB';return n+' B';}
function fmtTime(t){var d=new Date(t);return d.toLocaleDateString('id-ID',{day:'numeric',month:'short'})+' '+d.toLocaleTimeString('id-ID',{hour:'2-digit',minute:'2-digit'});}
function fileIco(n){var e=(n.split('.').pop()||'').toLowerCase();
  return {txt:'&#128196;',md:'&#128221;',py:'&#128013;',html:'&#127760;',js:'&#128220;',json:'&#129534;',csv:'&#128202;',pdf:'&#128213;'}[e]||'&#128196;';}

/* ================= state ================= */
var DEFAULT_SYS='Kamu adalah asisten AI lokal bernama "Kilat AI" yang berjalan sepenuhnya di komputer pengguna melalui Ollama. Jawab selalu dalam Bahasa Indonesia yang jelas, ramah, dan terstruktur; gunakan Markdown bila membantu. Jika pengguna meminta membuat, menyimpan, membaca, atau melihat file, gunakan tools yang tersedia (write_file, read_file, list_files) - file tersimpan di folder workspace dan dapat dilihat pengguna lewat panel Workspace. Untuk pertanyaan biasa, jawab langsung tanpa tools. Jika permintaan kurang jelas, tanya balik dengan sopan.';
var settings=Object.assign({ollamaUrl:'http://localhost:11434',model:'',systemPrompt:DEFAULT_SYS,temp:0.7,tools:true,arena:{enabled:false,models:[],judge:''},cloud:{enabled:false,base:'https://openrouter.ai/v1',key:'',model:''},light:false,whisper:''},loadLS('arena.settings',{}));
settings.arena=Object.assign({enabled:false,models:[],judge:''},settings.arena||{});
settings.cloud=Object.assign({enabled:false,base:'https://openrouter.ai/v1',key:'',model:''},settings.cloud||{});
var JUDGE_SYS='Kamu adalah juri kompetisi jawaban AI yang objektif. Tugasmu: membaca pertanyaan pengguna dan beberapa kandidat jawaban, lalu memilih SATU jawaban terbaik - yang paling akurat, lengkap, dan membantu. Jangan memihak model mana pun, termasuk dirimu sendiri. Balas dalam Bahasa Indonesia, langsung, dengan format yang diminta persis.';
var RECOMMENDED=['qwen3:8b','qwen3:4b','gemma3:12b','deepseek-r1:8b','qwen3:14b','llama3.2:3b','gpt-oss:20b','deepseek-r1:14b','gemma3:27b','qwen3:32b'];
function recommendModels(){
  var models=window._modelsCache||[];
  var names=models.map(function(m){return m.name;});
  var pick=[];
  RECOMMENDED.forEach(function(r){if(names.indexOf(r)>=0&&pick.length<3)pick.push(r);});
  if(pick.length<2){
    models.slice().sort(function(a,b){return (b.size||0)-(a.size||0);})
      .forEach(function(m){
        if(pick.length<3&&pick.indexOf(m.name)<0)pick.push(m.name);
      });
  }
  return pick;
}
function judgeRecommend(rec){
  var models=window._modelsCache||[];
  var names=models.map(function(m){return m.name;});
  var pref=['qwen3:8b','qwen3:4b','qwen3:14b','gemma3:12b'];
  for(var i=0;i<pref.length;i++){if(names.indexOf(pref[i])>=0)return pref[i];}
  if(rec&&rec.length)return rec[0];
  return settings.model||'';
}
var chats=loadLS('arena.chats',[]);
var serverOK=false;
var cur=null,streaming=false,controller=null,stick=true;

var msgCol=$('#msgCol'),msgBox=$('#messages'),emptyBox=$('#empty'),input=$('#input'),
    sendBtn=$('#sendBtn'),modelSel=$('#modelSel'),connBanner=$('#connBanner'),connText=$('#connText');

/* ================= markdown mini ================= */
function md(src){
  var codes=[];
  src=String(src==null?'':src);
  src=src.replace(/```([\w+#-]*)[ \t]*\n?([\s\S]*?)(```|$)/g,function(m,lang,code){
    codes.push({lang:lang,code:code.replace(/\n$/,'')});return '\x00C'+(codes.length-1)+'\x00';});
  src=esc(src);
  function inline(s){
    s=s.replace(/`([^`\n]+)`/g,function(m,c){return '<code>'+c+'</code>';});
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    s=s.replace(/(^|[\s(>])\*([^*\n]+)\*/g,'$1<em>$2</em>');
    s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return s;
  }
  var lines=src.split('\n'),out=[],i=0,para=[];
  function flush(){if(para.length){out.push('<p>'+inline(para.join('<br>'))+'</p>');para=[];}}
  while(i<lines.length){
    var l=lines[i],m;
    if(m=l.match(/^\x00C(\d+)\x00\s*$/)){
      flush();var b=codes[+m[1]];
      out.push('<div class="codeblock"><div class="codehead"><span>'+esc(b.lang||'text')+'</span>'+
        '<button class="copycode" type="button">&#128203; Salin</button></div>'+
        '<pre><code>'+esc(b.code)+'</code></pre></div>');
      i++;continue;}
    if(m=l.match(/^(#{1,6})\s+(.*)$/)){
      flush();var h=Math.min(m[1].length+2,5);
      out.push('<h'+h+'>'+inline(m[2])+'</h'+h+'>');i++;continue;}
    if(/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l)){flush();out.push('<hr>');i++;continue;}
    if(/^&gt;/.test(l)){
      flush();var q=[];
      while(i<lines.length&&/^&gt;/.test(lines[i])){q.push(lines[i].replace(/^&gt;\s?/,''));i++;}
      out.push('<blockquote>'+inline(q.join('<br>'))+'</blockquote>');continue;}
    if(/^\s*[-*+]\s+/.test(l)){
      flush();var it=[];
      while(i<lines.length&&/^\s*[-*+]\s+/.test(lines[i])){it.push('<li>'+inline(lines[i].replace(/^\s*[-*+]\s+/,''))+'</li>');i++;}
      out.push('<ul>'+it.join('')+'</ul>');continue;}
    if(/^\s*\d+[.)]\s+/.test(l)){
      flush();var it2=[];
      while(i<lines.length&&/^\s*\d+[.)]\s+/.test(lines[i])){it2.push('<li>'+inline(lines[i].replace(/^\s*\d+[.)]\s+/,''))+'</li>');i++;}
      out.push('<ol>'+it2.join('')+'</ol>');continue;}
    if(l.indexOf('|')>=0&&i+1<lines.length&&/^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$/.test(lines[i+1])){
      flush();
      function cells(row){var c=row.split('|').map(function(s){return s.trim();});
        if(c.length&&!c[0])c.shift();if(c.length&&!c[c.length-1])c.pop();return c;}
      var head=cells(l);i+=2;var rows=[];
      while(i<lines.length&&lines[i].indexOf('|')>=0&&lines[i].trim()!==''){rows.push(cells(lines[i]));i++;}
      out.push('<div class="tablewrap"><table><thead><tr>'+head.map(function(x){return '<th>'+inline(x)+'</th>';}).join('')+
        '</tr></thead><tbody>'+rows.map(function(r){return '<tr>'+r.map(function(x){return '<td>'+inline(x)+'</td>';}).join('')+'</tr>';}).join('')+
        '</tbody></table></div>');
      continue;}
    if(l.trim()===''){flush();i++;continue;}
    para.push(l);i++;
  }
  flush();
  return out.join('\n');
}

/* ================= render ================= */
function renderSide(){
  var el=$('#chatList');
  el.innerHTML=chats.map(function(c){
    return '<div class="chat-item'+(cur&&cur.id===c.id?' active':'')+'" data-id="'+c.id+'">'+
      '<div class="ci-title">'+(esc(c.title)||'Obrolan baru')+'</div>'+
      '<div class="ci-time">'+fmtTime(c.created)+'</div>'+
      '<button class="ci-del" data-del="'+c.id+'" title="Hapus obrolan">&#128465;&#65039;</button></div>';
  }).join('')||'<div class="files-empty" style="padding:14px 10px">Belum ada obrolan.<br>Tekan &ldquo;＋ Obrolan Baru&rdquo;.</div>';
  $('#footStat').textContent=chats.length+' obrolan'+(settings.model?' &bull; '+settings.model.split(':')[0]:'');
}
function updateEmpty(){
  var has=!!(cur&&cur.messages.length);
  emptyBox.hidden=has;
  msgBox.style.display=has?'flex':'none';
}
function evHtml(ev){
  var ico=ev.status==='run'?'<span class="spin">&#10227;</span>':(ev.status==='ok'?'&#9989;':'&#10060;');
  var arg=(ev.args&&(ev.args.file_path||ev.args.path||ev.args.name||ev.args.query))||'';
  var det='ARGUMEN\n'+JSON.stringify(ev.args||{},null,1)+'\n\nHASIL\n'+(ev.result||'&hellip;');
  return '<div class="ev">'+ico+'<span class="ev-name">'+esc(ev.name)+'</span>'+
    (arg?'<code>'+esc(arg)+'</code>':'')+
    '<button class="linkbtn ev-toggle" type="button">detail</button>'+
    '<pre class="ev-det" hidden>'+esc(det)+'</pre></div>';
}
function paintAI(wrap,m){
  var evs=wrap.querySelector('.evs');
  if(m.events&&m.events.length){
    evs.style.display='flex';evs.innerHTML=m.events.map(evHtml).join('');
  }else{evs.style.display='none';evs.innerHTML='';}
  var el=wrap.querySelector('.md');
  if(!m.content&&!m.error&&!m.done){el.innerHTML='<div class="dots"><span></span><span></span><span></span></div>';return;}
  var html=md(m.content);
  if(!m.done&&streaming&&m.content)html+='<span class="cursor"></span>';
  if(m.error)html+='<div class="errnote">&#9888;&#65039; '+esc(m.error)+'</div>';
  el.innerHTML=html;
}
function appendMsg(m){
  var wrap=document.createElement('div');
  if(m.role==='arena'){
    wrap.className='msg ai';
    wrap.innerHTML='<div class="avatar">&#127951;&#65039;</div><div class="ai-main"><div class="arena-box"></div></div>';
    wrap.__arena=m;paintArena(wrap,m);
    msgCol.appendChild(wrap);
    if(stick)scrollBottom();
    return wrap;
  }
  if(m.role==='user'){
    wrap.className='msg user';
    var b=document.createElement('div');b.className='bubble';b.textContent=m.content;
    wrap.appendChild(b);
  }else{
    wrap.className='msg ai';
    wrap.innerHTML='<div class="avatar">&#9889;</div><div class="ai-main">'+
      '<div class="evs" style="display:none"></div><div class="md"></div>'+
      '<div class="ai-actions"><button class="linkbtn copymsg" type="button">&#128203; Salin</button>'+
      '<button class="linkbtn speakmsg" type="button">&#128266; Bacakan</button>'+
      '<span class="aimeta">'+(m.done===false?'':'')+'</span></div></div>';
    paintAI(wrap,m);
  }
  msgCol.appendChild(wrap);
  if(stick)scrollBottom();
  return wrap;
}
function renderMsgs(){
  msgCol.innerHTML='';
  if(cur){cur.messages.forEach(function(m){appendMsg(m);});}
  updateEmpty();
  scrollBottom(true);
}
function scrollBottom(force){if(force)stick=true;msgBox.scrollTop=msgBox.scrollHeight;}
msgBox.addEventListener('scroll',function(){
  stick=msgBox.scrollTop+msgBox.clientHeight>msgBox.scrollHeight-90;});

/* ================= obrolan ================= */
function newChat(){
  stopStream();
  cur={id:uid(),title:'',created:Date.now(),messages:[]};
  chats.unshift(cur);saveLS('arena.chats',chats);syncServer();
  renderSide();renderMsgs();input.focus();
}
function openChat(id){
  stopStream();
  for(var i=0;i<chats.length;i++){if(chats[i].id===id){cur=chats[i];break;}}
  renderSide();
  document.body.classList.remove('side-open');
  if(serverOK&&cur&&cur._srv&&!cur.messages.length){loadConvServer(id);return;}
  renderMsgs();
}
function loadConvServer(id){
  fetch('/api/history?id='+encodeURIComponent(id)).then(function(r){return r.json();})
   .then(function(d){
     if(cur&&cur.id===id&&d&&d.messages){cur.messages=d.messages;cur._srv=false;}
     renderMsgs();
   }).catch(function(){renderMsgs();});
}
function syncServer(){
  if(!serverOK||!cur)return;
  if(!cur.messages||!cur.messages.length)return;
  if(!chats.some(function(c){return c.id===cur.id;}))return;
  try{
    fetch('/api/history',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:cur.id,title:cur.title||'',created:cur.created,messages:cur.messages})})
      .catch(function(){});
  }catch(e){}
}
function bootHistory(){
  fetch('/api/history').then(function(r){return r.json();}).then(function(d){
    serverOK=true;
    var list=(d&&d.conversations)||[];
    if(list.length){
      chats=list.map(function(c){return {id:c.id,title:c.title,created:c.created,messages:[],_srv:true};});
      cur=chats[0];
    }
    renderSide();
    if(!chats.length)newChat();
    else{renderMsgs();if(cur&&cur._srv)loadConvServer(cur.id);}
  }).catch(function(){
    serverOK=false;
    renderSide();
    if(!chats.length)newChat();
    else{cur=chats[0];renderMsgs();}
  });
}
function delChat(ev,id){
  ev.stopPropagation();
  chats=chats.filter(function(c){return c.id!==id;});
  saveLS('arena.chats',chats);syncServer();
  if(serverOK)fetch('/api/history?id='+encodeURIComponent(id),{method:'DELETE'}).catch(function(){});
  if(!chats.length){newChat();return;}
  if(!cur||cur.id===id)cur=chats[0];
  renderSide();renderMsgs();
}
function stopStream(){
  if(controller){try{controller.abort();}catch(e){}}
  controller=null;streaming=false;setSendState();
}
function setSendState(){
  if(streaming){sendBtn.innerHTML='&#9632;';sendBtn.classList.add('stop');sendBtn.title='Hentikan';}
  else{sendBtn.innerHTML='&#10148;';sendBtn.classList.remove('stop');sendBtn.title='Kirim';}
}

/* ================= kirim & streaming ================= */
function sendCurrent(){
  var t=input.value.trim();
  if(streaming||!t)return;
  input.value='';autoGrow();
  submitText(t);
}
function submitText(text){
  if(settings.arena.enabled&&!settings.cloud.enabled)sendArena(text);else sendMsg(text);
}
function sendMsg(text){
  if(settings.cloud.enabled){
    if(!settings.cloud.key||!settings.cloud.model){toast('&#9888;&#65039; Lengkapi API key &amp; nama model di Pengaturan &gt; Cloud');return;}
  }else if(!settings.model){toast('&#9888;&#65039; Pilih model dulu &mdash; pastikan Ollama berjalan');return;}
  if(!cur)newChat();
  cur.messages.push({role:'user',content:text});
  if(!cur.title){cur.title=text.slice(0,60);renderSide();}
  saveLS('arena.chats',chats);syncServer();
  updateEmpty();
  appendMsg(cur.messages[cur.messages.length-1]);

  var ai={role:'assistant',content:'',events:[],done:false,error:null};
  cur.messages.push(ai);
  var wrap=appendMsg(ai);
  streaming=true;setSendState();

  var hist=buildHist(cur.messages.slice(0,-1));

  controller=new AbortController();
  var lastEv=null,pending=false;
  function paint(){pending=false;paintAI(wrap,ai);if(stick)scrollBottom();}
  function queue(){if(!pending){pending=true;setTimeout(paint,70);}}

  fetch('/api/chat',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    signal:controller.signal,
    body:JSON.stringify({
      model:settings.cloud.enabled?(settings.cloud.model||''):settings.model,
      messages:hist,system_prompt:settings.systemPrompt,
      temperature:settings.temp,tools:settings.tools&&!settings.cloud.enabled,
      ollama_url:settings.ollamaUrl,
      api_base:settings.cloud.enabled?settings.cloud.base:'',
      api_key:settings.cloud.enabled?settings.cloud.key:''})
  }).then(function(res){
    if(!res.ok)throw new Error('Server error '+res.status);
    var reader=res.body.getReader(),dec=new TextDecoder(),buf='';
    function pump(){
      return reader.read().then(function(r){
        if(r.done)return;
        buf+=dec.decode(r.value,{stream:true});
        var idx;
        while((idx=buf.indexOf('\n'))>=0){
          var line=buf.slice(0,idx).trim();buf=buf.slice(idx+1);
          if(!line)continue;
          var ev;try{ev=JSON.parse(line);}catch(e){continue;}
          if(ev.t==='token'){ai.content+=ev.v;queue();}
          else if(ev.t==='tool'){lastEv={name:ev.name,args:ev.args,status:'run',result:''};ai.events.push(lastEv);queue();}
          else if(ev.t==='toolresult'){
            if(lastEv){lastEv.status=ev.ok?'ok':'err';lastEv.result=ev.v;lastEv=null;}
            queue();
            if(ev.ok&&ev.name==='write_file')toast('&#128193; File dibuat di workspace');
          }
          else if(ev.t==='notice'){toast(ev.v);}
          else if(ev.t==='error'){ai.error=ev.v;queue();}
          else if(ev.t==='done'){ai.done=true;queue();}
        }
        return pump();
      });
    }
    return pump();
  }).catch(function(e){
    if(e&&e.name==='AbortError'){ai.content+=(ai.content?'\n\n':'')+'_&#9209; Dihentikan._';}
    else{ai.error=(e&&e.message)||'Koneksi ke aplikasi gagal.';}
  }).then(function(){
    ai.done=true;streaming=false;controller=null;setSendState();paint();
    saveLS('arena.chats',chats);syncServer();renderSide();
    if(ai.events&&ai.events.length)refreshFiles();
  });
}

/* ================= mode arena ================= */
function buildHist(msgs){
  var out=[];
  msgs.forEach(function(m){
    if(m.role==='user'&&m.content)out.push({role:'user',content:m.content});
    else if(m.role==='assistant'&&m.content)out.push({role:'assistant',content:m.content});
    else if(m.role==='arena'&&m.done){
      var w=amWinner(m);
      if(w&&w.content)out.push({role:'assistant',content:w.content});
    }
  });
  return out.slice(-40);
}
function amWinner(m){
  if(!m.answers||!m.answers.length)return null;
  var i=0;
  if(m.verdict&&typeof m.verdict.pick==='number'&&m.verdict.pick>=0&&m.verdict.pick<m.answers.length)i=m.verdict.pick;
  return m.answers[i];
}
function streamChat(model,messages,opts,onToken,onEnd,onAbort){
  opts=opts||{};
  controller=new AbortController();
  var body={model:model,messages:messages,tools:false,
    temperature:opts.temp==null?settings.temp:opts.temp,ollama_url:settings.ollamaUrl,
    system_prompt:opts.judge?JUDGE_SYS:settings.systemPrompt,keep_alive:0};
  fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    signal:controller.signal,body:JSON.stringify(body)})
    .then(function(res){
      if(!res.ok)throw new Error('Server error '+res.status);
      var reader=res.body.getReader(),dec=new TextDecoder(),buf='';
      function pump(){return reader.read().then(function(r){
        if(r.done)return;
        buf+=dec.decode(r.value,{stream:true});
        var idx;
        while((idx=buf.indexOf('\n'))>=0){
          var line=buf.slice(0,idx).trim();buf=buf.slice(idx+1);
          if(!line)continue;
          var ev;try{ev=JSON.parse(line);}catch(e){continue;}
          if(ev.t==='token')onToken(ev.v);
          else if(ev.t==='error')throw new Error(ev.v);
        }
        return pump();
      });}
      return pump();
    })
    .then(function(){onEnd(null);})
    .catch(function(e){
      if(e&&e.name==='AbortError'){if(onAbort)onAbort();}
      else onEnd((e&&e.message)||'Koneksi gagal');
    });
}
var arenaStopped=false;
function sendArena(text){
  var models=settings.arena.models.slice(0,4);
  if(models.length<2){toast('&#127951;&#65039; Mode Arena butuh 2-4 model - buka pengaturan Arena');return;}
  if(!cur)newChat();
  cur.messages.push({role:'user',content:text});
  if(!cur.title){cur.title=text.slice(0,60);renderSide();}
  saveLS('arena.chats',chats);syncServer();
  updateEmpty();
  appendMsg(cur.messages[cur.messages.length-1]);

  var am={role:'arena',q:text,answers:[],verdict:null,judging:false,done:false,active:-1};
  cur.messages.push(am);
  var wrap=appendMsg(am);
  streaming=true;setSendState();arenaStopped=false;

  var base=buildHist(cur.messages.slice(0,-2));
  var letters='ABCDEFGH';

  function runNext(i){
    if(arenaStopped){am.done=true;finish();return;}
    if(i>=models.length){runJudge();return;}
    var ans={model:models[i],content:'',error:null};
    am.answers.push(ans);am.active=i;paintArena(wrap,am);
    if(stick)scrollBottom();
    var pending=false;
    function paint(){pending=false;paintArena(wrap,am);if(stick)scrollBottom();}
    streamChat(models[i],base.concat([{role:'user',content:text}]),{},function(t){
      ans.content+=t;
      if(!pending){pending=true;setTimeout(paint,70);}
    },function(err){
      ans.error=err||null;am.active=-1;paintArena(wrap,am);runNext(i+1);
    },function(){
      ans.content+='\n\n_(dihentikan)_';arenaStopped=true;am.active=-1;am.done=true;finish();
    });
  }

  function runJudge(){
    var okd=am.answers.filter(function(a){return a.content&&!a.error;});
    if(okd.length<2||!settings.arena.judge){am.done=true;finish();return;}
    var cand=okd.map(function(a,idx){return '['+letters[idx]+'] model: '+a.model+'\n'+String(a.content).slice(0,2500);}).join('\n\n---\n\n');
    var q='PERTANYAAN PENGGUNA:\n'+text+'\n\nKANDIDAT JAWABAN:\n\n'+cand+
      '\n\nTugas: pilih SATU jawaban terbaik untuk pertanyaan pengguna - yang paling akurat, lengkap, dan membantu. Balas PERSIS format:\nJAWABAN TERBAIK: <huruf>\nALASAN: <satu sampai dua kalimat>';
    am.judging=true;am.active=-1;paintArena(wrap,am);
    if(stick)scrollBottom();
    var jt='';
    streamChat(settings.arena.judge,[{role:'user',content:q}],{judge:true,temp:0.1},function(t){jt+=t;},
    function(err){
      am.judging=false;
      if(!err){
        var mm=jt.match(/JAWABAN TERBAIK\s*[:=]\s*\(?([A-H])\)?/i);
        var rm=jt.match(/ALASAN\s*[:=]\s*([\s\S]+)/i);
        if(mm){
          var idx='ABCDEFGH'.indexOf(mm[1].toUpperCase());
          if(idx>=0&&idx<okd.length){
            am.verdict={pick:am.answers.indexOf(okd[idx]),judge:settings.arena.judge,
              reason:(rm?rm[1]:'').trim().slice(0,300),manual:false};
          }
        }
      }
      am.done=true;finish();
    },function(){am.judging=false;am.done=true;finish();});
  }

  function finish(){
    streaming=false;setSendState();
    am.done=true;am.judging=false;am.active=-1;
    am.answers.forEach(function(a){a.content=String(a.content||'').slice(0,6000);});
    paintArena(wrap,am);
    saveLS('arena.chats',chats);syncServer();renderSide();
  }

  runNext(0);
}
function paintArena(wrap,am){
  var box=wrap.querySelector('.arena-box');if(!box)return;
  var h='';
  if(am.verdict){
    var w=am.answers[am.verdict.pick];
    h+='<div class="verdict">&#127942; <b>Jawaban terbaik: '+esc(w?w.model:'?')+'</b> '+
      (am.verdict.manual?'<span class="ac-status">(dipilih manual)</span>':'<span class="ac-status">juri: '+esc(am.verdict.judge||'-')+'</span>')+
      (am.verdict.reason?'<br><span style="color:#c7cde0">&#128161; '+esc(am.verdict.reason)+'</span>':'')+'</div>';
  }else if(am.judging){
    h+='<div class="verdict">&#9203; <b>Juri ('+esc(settings.arena.judge)+') sedang menilai jawaban&hellip;</b></div>';
  }else if(am.done){
    h+='<div class="verdict">&#129300; Juri belum memutuskan - klik tombol <b>&#128077; Pilih</b> pada jawaban yang paling Anda suka.</div>';
  }
  (am.answers||[]).forEach(function(a,i){
    var isActive=am.active===i;
    var isWin=am.verdict&&am.verdict.pick===i;
    var collapsed=am.verdict&&!isWin;
    var status=a.error?'<span style="color:var(--err)">&#10060; gagal</span>':
      (isActive?'<span class="spin">&#10227;</span> <span class="ac-status">menjawab&hellip;</span>':
      (isWin?'<span class="wintag">&#127942; TERBAIK</span>':'<span class="ac-status">selesai</span>'));
    var bodyHtml=a.error?'<div class="errnote">&#9888;&#65039; '+esc(a.error)+'</div>':
      (isActive&&!a.content?'<div class="dots"><span></span><span></span><span></span></div>':md(a.content||''));
    h+='<div class="arena-card'+(isWin?' win':'')+'">'+
      '<div class="ac-head"><span class="ac-name">'+esc(a.model)+'</span>'+status+
      '<button class="pickbtn" data-pick="'+i+'" type="button">&#128077; Pilih</button></div>'+
      '<div class="ac-body"'+(collapsed?' hidden':'')+'>'+bodyHtml+'</div></div>';
  });
  if(!(am.answers&&am.answers.length))h+='<div class="dots"><span></span><span></span><span></span></div>';
  box.innerHTML=h;
}
function updateArenaChip(){
  var b=$('#arenaBtn');var on=settings.arena.enabled&&settings.arena.models.length>=2;
  b.innerHTML='&#127951;&#65039; Arena: '+(on?'ON ('+settings.arena.models.length+')':'OFF');
  b.classList.toggle('off',!on);
  updateCloudUI();
}
function updateCloudUI(){
  var arOn=settings.arena.enabled&&settings.arena.models.length>=2;
  var clOn=settings.cloud&&settings.cloud.enabled;
  $('#arenaBtn').style.display=clOn?'none':'';
  if(clOn){
    var cm=settings.cloud.model||'cloud-model';
    modelSel.innerHTML='<option value="'+esc(cm)+'">&#9729;&#65039; '+esc(cm)+'</option>';
    modelSel.disabled=true;modelSel.title='Mode cloud aktif - ubah di Pengaturan';
    $('#toolsBtn').style.display='none';
    input.placeholder='Ketik pesan (mode cloud)\u2026';
    $('#footMode').innerHTML='&#9729;&#65039; <b>Mode cloud</b> &mdash; percakapan keluar ke penyedia API.';
  }else{
    modelSel.disabled=arOn;
    modelSel.title=arOn?'Mode Arena aktif - beberapa model menjawab':'Pilih model AI';
    $('#toolsBtn').style.display=arOn?'none':'';
    input.placeholder=arOn?'Ketik pesan (dijawab '+settings.arena.models.length+' model, juri memilih terbaik)\u2026'
      :'Ketik pesan\u2026  (Enter kirim \u2022 Shift+Enter baris baru)';
    $('#footMode').innerHTML='<b>100% lokal &amp; privat</b> &mdash; percakapan tidak keluar dari komputer Anda.';
  }
}
function uploadFile(f){
  if(f.size>5*1024*1024){toast('&#9888;&#65039; '+f.name+' terlalu besar (maks 5 MB)');return;}
  toast('&#8205;');$('#toast').hidden=true;
  fetch('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error)toast('&#9888;&#65039; '+d.error);
      else{toast('&#128229; '+d.name+' terupload ke workspace');refreshFiles();}
    }).catch(function(){toast('&#9888;&#65039; Upload gagal');});
}
$('#uploadBtn').addEventListener('click',function(){$('#fileInput').click();});
$('#fileInput').addEventListener('change',function(){
  Array.prototype.forEach.call(this.files,uploadFile);this.value='';
});
window.addEventListener('dragover',function(e){e.preventDefault();});
window.addEventListener('drop',function(e){
  e.preventDefault();
  if(e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files.length){
    Array.prototype.forEach.call(e.dataTransfer.files,uploadFile);
    $('#filesPanel').hidden=false;
  }
});
function applyTheme(){
  document.body.classList.toggle('light',!!settings.light);
  $('#themeBtn').innerHTML=settings.light?'&#9788;':'&#127769;';
}
$('#themeBtn').addEventListener('click',function(){
  settings.light=!settings.light;saveLS('arena.settings',settings);applyTheme();
});
function renderArenaChecks(){
  var box=$('#arModels');var models=window._modelsCache||[];
  var sel=settings.arena.models.slice();
  if(!sel.length)sel=recommendModels();
  box.innerHTML=models.length?models.map(function(m){
    var c=sel.indexOf(m.name)>=0?' checked':'';
    var rec=RECOMMENDED.indexOf(m.name)>=0;
    var ram=(m.size<3.5e9)?'RAM 8 GB':(m.size<7e9)?'RAM 16 GB':(m.size<12e9)?'RAM 24 GB':'RAM 32 GB+';
    return '<label class="model-check"><input type="checkbox" data-ar="'+esc(m.name)+'"'+c+
      '><span class="mc-name">'+esc(m.name)+(rec?' &#11088;':'')+'</span><span class="mc-size">'+
      fmtSize(m.size||0)+' &bull; '+ram+(rec?' &bull; direkomendasikan':'')+'</span></label>';
  }).join(''):'<div class="files-empty">Belum ada model terpasang.<br>Install dulu lewat Ollama.</div>';
}
function renderJudgeSel(){
  var models=window._modelsCache||[];
  var v=settings.arena.judge||'';
  if(!v||!models.some(function(m){return m.name===v;}))v=judgeRecommend(recommendModels());
  $('#arJudge').innerHTML=models.map(function(m){
    return '<option value="'+esc(m.name)+'"'+(m.name===v?' selected':'')+'>'+esc(m.name)+'</option>';
  }).join('');
}
$('#arenaBtn').addEventListener('click',function(){
  $('#arEnable').checked=!!settings.arena.enabled;
  renderArenaChecks();renderJudgeSel();
  $('#arenaModal').hidden=false;
});
$('#saveArenaBtn').addEventListener('click',function(){
  var sel=[];
  document.querySelectorAll('#arModels input[data-ar]').forEach(function(cb){
    if(cb.checked)sel.push(cb.getAttribute('data-ar'));
  });
  if(sel.length>4){toast('&#9888;&#65039; Maksimal 4 model peserta');return;}
  if($('#arEnable').checked&&sel.length<2){toast('&#9888;&#65039; Pilih minimal 2 model peserta');return;}
  settings.arena.enabled=$('#arEnable').checked;
  settings.arena.models=sel;
  settings.arena.judge=$('#arJudge').value||'';
  saveLS('arena.settings',settings);
  $('#arenaModal').hidden=true;
  updateArenaChip();renderSide();
  toast(settings.arena.enabled?'&#127951;&#65039; Mode Arena aktif - '+sel.length+' model peserta':'Mode Arena nonaktif');
});
$('#arRecBtn').addEventListener('click',function(){
  var rec=recommendModels();
  document.querySelectorAll('#arModels input[data-ar]').forEach(function(cb){
    cb.checked=rec.indexOf(cb.getAttribute('data-ar'))>=0;
  });
  var j=judgeRecommend(rec);
  if(j)$('#arJudge').value=j;
  toast('&#11088; Rekomendasi: '+rec.join(' + '));
});

/* ================= model ================= */
function loadModels(){
  fetch('/api/models?url='+encodeURIComponent(settings.ollamaUrl))
    .then(function(r){return r.json();})
    .then(function(d){
      var models=d.models||[],err=d.error||'';
      window._modelsCache=models;
      modelSel.innerHTML='';
      if(err){
        connBanner.hidden=false;
        connText.innerHTML='&#9888;&#65039; <b>Ollama tidak terdeteksi.</b> '+esc(err);
      }else if(!models.length){
        connBanner.hidden=false;
        connText.innerHTML='&#9888;&#65039; <b>Belum ada model.</b> Buka terminal dan jalankan '+
          '<code>ollama pull llama3.2</code>, tunggu sampai selesai, lalu tekan Muat ulang.';
      }else{connBanner.hidden=true;}
      if(models.length){
        modelSel.innerHTML=models.map(function(m){
          var sz=m.size?' &bull; '+(m.size/1073741824).toFixed(1)+' GB':'';
          return '<option value="'+esc(m.name)+'">'+esc(m.name)+sz+(RECOMMENDED.indexOf(m.name)>=0?' \u2b50':'')+'</option>';}).join('');
        var found=models.some(function(m){return m.name===settings.model;});
        if(!found){settings.model=models[0].name;saveLS('arena.settings',settings);}
        modelSel.value=settings.model;
        settings.arena.models=(settings.arena.models||[]).filter(function(n){return models.some(function(m){return m.name===n;});}).slice(0,4);
        if(!models.some(function(m){return m.name===settings.arena.judge;})){settings.arena.judge=settings.model;}
        saveLS('arena.settings',settings);
      }else{
        modelSel.innerHTML='<option value="">&mdash; tidak ada model &mdash;</option>';
        settings.model='';saveLS('arena.settings',settings);
      }
      updateArenaChip();updateDemoBadge();renderSide();
    }).catch(function(){
      connBanner.hidden=false;
      connText.innerHTML='&#9888;&#65039; Gagal memuat daftar model.';
    });
}
function updateDemoBadge(){
  $('#demoBadge').hidden=!(settings.model||'').toLowerCase().indexOf('demo')===0;
}

/* ================= workspace ================= */
function refreshFiles(){
  fetch('/api/files').then(function(r){return r.json();}).then(function(d){
    var files=d.files||[],fl=$('#fileList');
    fl.innerHTML=files.length?files.map(function(f){
      return '<div class="file" data-name="'+esc(f.name)+'">'+
        '<span>'+fileIco(f.name)+'</span><span class="fname">'+esc(f.name)+'</span>'+
        '<span class="fsize">'+fmtSize(f.size)+'</span></div>';
    }).join(''):'<div class="files-empty">Belum ada file.<br>Coba minta AI: &ldquo;buatkan file catatan.txt&rdquo;</div>';
  }).catch(function(){});
}
var viewRaw=false,viewText='';
function openFile(name){
  fetch('/api/file?name='+encodeURIComponent(name)).then(function(r){
    if(!r.ok)throw new Error('gagal');return r.text();
  }).then(function(t){
    viewText=t;viewRaw=false;
    $('#viewName').textContent=name;
    $('#viewDl').href='/api/file?name='+encodeURIComponent(name)+'&dl=1';
    renderView((name.split('.').pop()||'').toLowerCase());
    $('#viewerModal').hidden=false;
  }).catch(function(){toast('&#9888;&#65039; Gagal membuka file');});
}
function renderView(ext){
  var body=$('#viewBody'),tog=$('#viewToggle');
  var renderable=(ext==='md'||ext==='html'||ext==='htm');
  tog.style.display=renderable?'':'none';
  tog.innerHTML=viewRaw?'&#128065; Lihat hasil':'&#128196; Lihat mentah';
  if(!renderable||viewRaw){body.className='';body.textContent=viewText;return;}
  if(ext==='md'){body.className='md';body.innerHTML=md(viewText);}
  else{
    body.className='';
    body.innerHTML='<iframe sandbox style="width:100%;height:52vh;border:1px solid var(--border);border-radius:11px;background:#fff" srcdoc="'+esc(viewText)+'"></iframe>';
  }
}

/* ================= suara (STT & TTS) ================= */
var rec=null,recOn=false,mediaRec=null,mediaChunks=[];
function setMic(on){
  recOn=on;
  var b=$('#micBtn');
  b.classList.toggle('rec',on);
  b.title=on?'Sedang merekam - klik untuk berhenti':'Bicara (input suara)';
  b.innerHTML=on?'&#9209;':'&#127908;';
}
function startWebSpeech(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){toast('&#9888;&#65039; Browser tidak mendukung input suara - pakai Chrome/Edge, atau pasang Whisper (lihat PANDUAN)');return;}
  rec=new SR();
  rec.lang='id-ID';rec.continuous=true;rec.interimResults=true;
  rec.onresult=function(e){
    var fin='';
    for(var i=e.resultIndex;i<e.results.length;i++){
      if(e.results[i].isFinal)fin+=e.results[i][0].transcript;
    }
    if(fin){input.value=(input.value?input.value+' ':'')+fin.trim();autoGrow();}
  };
  rec.onerror=function(e){
    setMic(false);
    if(e.error==='not-allowed')toast('&#9888;&#65039; Izinkan akses mikrofon di browser');
    else if(e.error==='network')toast('&#9888;&#65039; Engine suara browser butuh internet - untuk offline pasang Whisper (PANDUAN)');
  };
  rec.onend=function(){if(recOn){try{rec.start();}catch(e){setMic(false);}}};
  try{rec.start();setMic(true);}catch(e){toast('&#9888;&#65039; Gagal memulai rekaman');}
}
function startWhisper(){
  if(!navigator.mediaDevices||!window.MediaRecorder){toast('&#9888;&#65039; Browser tidak mendukung perekaman audio');return;}
  navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
    mediaChunks=[];
    mediaRec=new MediaRecorder(stream);
    mediaRec.ondataavailable=function(e){if(e.data.size)mediaChunks.push(e.data);};
    mediaRec.onstop=function(){
      stream.getTracks().forEach(function(t){t.stop();});
      var blob=new Blob(mediaChunks,{type:mediaRec.mimeType||'audio/webm'});
      if(blob.size<1200){toast('&#127908; Rekaman terlalu pendek');return;}
      toast('&#8987; Mengubah suara jadi teks (Whisper lokal)&hellip;');
      fetch('/api/stt',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:blob})
        .then(function(r){return r.json();})
        .then(function(d){
          if(d.error){toast('&#9888;&#65039; '+d.error);return;}
          if(d.text){input.value=(input.value?input.value+' ':'')+d.text;autoGrow();input.focus();}
        }).catch(function(){toast('&#9888;&#65039; Gagal memproses audio');});
    };
    mediaRec.start();
    setMic(true);
  }).catch(function(){toast('&#9888;&#65039; Izinkan akses mikrofon di browser');});
}
$('#micBtn').addEventListener('click',function(){
  if(recOn){
    setMic(false);
    if(rec){try{rec.stop();}catch(e){}}
    if(mediaRec&&mediaRec.state!=='inactive')mediaRec.stop();
    return;
  }
  if(settings.whisper)startWhisper();else startWebSpeech();
});
var idVoice=null;
function pickVoice(){
  var vs=window.speechSynthesis?speechSynthesis.getVoices():[];
  idVoice=vs.filter(function(v){return /^id(-|_)/i.test(v.lang);})[0]
    ||vs.filter(function(v){return /indones/i.test(v.name);})[0]||null;
}
if(window.speechSynthesis){pickVoice();speechSynthesis.onvoiceschanged=pickVoice;}
function speakText(t){
  if(!window.speechSynthesis){toast('Browser tidak mendukung text-to-speech');return;}
  speechSynthesis.cancel();
  var u=new SpeechSynthesisUtterance(String(t).slice(0,4000));
  u.lang='id-ID';if(idVoice)u.voice=idVoice;
  speechSynthesis.speak(u);
}

/* ================= toast ================= */
var toastTimer=null;
function toast(html){
  var t=$('#toast');t.innerHTML=html;t.hidden=false;
  if(toastTimer)clearTimeout(toastTimer);
  toastTimer=setTimeout(function(){t.hidden=true;},2800);
}

/* ================= event wiring ================= */
function autoGrow(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,200)+'px';}
input.addEventListener('input',autoGrow);
input.addEventListener('keydown',function(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendCurrent();}
});
sendBtn.addEventListener('click',function(){
  if(streaming){if(controller)controller.abort();}
  else sendCurrent();
});
$('#newChatBtn').addEventListener('click',newChat);
$('#chatList').addEventListener('click',function(e){
  var del=e.target.closest('[data-del]');
  if(del){delChat(e,del.getAttribute('data-del'));return;}
  var item=e.target.closest('.chat-item');
  if(item)openChat(item.getAttribute('data-id'));
});
$('#chips').addEventListener('click',function(e){
  var b=e.target.closest('button[data-q]');
  if(b)submitText(b.getAttribute('data-q'));
});
$('#refreshModels').addEventListener('click',loadModels);
$('#reloadModels').addEventListener('click',loadModels);
modelSel.addEventListener('change',function(){
  settings.model=modelSel.value;saveLS('arena.settings',settings);
  updateDemoBadge();renderSide();
});
function updateToolsChip(){
  var b=$('#toolsBtn');
  b.innerHTML='&#128295; Tools: '+(settings.tools?'ON':'OFF');
  b.classList.toggle('off',!settings.tools);
}
$('#toolsBtn').addEventListener('click',function(){
  settings.tools=!settings.tools;saveLS('arena.settings',settings);updateToolsChip();
});
$('#filesBtn').addEventListener('click',function(){
  var p=$('#filesPanel');p.hidden=!p.hidden;
  if(!p.hidden)refreshFiles();
});
$('#closeFilesBtn').addEventListener('click',function(){$('#filesPanel').hidden=true;});
$('#refreshFilesBtn').addEventListener('click',refreshFiles);
$('#fileList').addEventListener('click',function(e){
  var f=e.target.closest('.file');
  if(f)openFile(f.getAttribute('data-name'));
});
$('#viewToggle').addEventListener('click',function(){
  viewRaw=!viewRaw;
  renderView(($('#viewName').textContent.split('.').pop()||'').toLowerCase());
});
$('#openSide').addEventListener('click',function(){document.body.classList.add('side-open');});
$('#closeSide').addEventListener('click',function(){document.body.classList.remove('side-open');});

/* pengaturan */
$('#settingsBtn').addEventListener('click',function(){
  $('#setUrl').value=settings.ollamaUrl;
  $('#setSys').value=settings.systemPrompt;
  $('#setTemp').value=settings.temp;$('#tempVal').textContent=settings.temp;
  $('#setTools').checked=settings.tools;
  $('#setCloud').checked=!!settings.cloud.enabled;
  $('#setCBase').value=settings.cloud.base||'';
  $('#setCKey').value=settings.cloud.key||'';
  $('#setCModel').value=settings.cloud.model||'';
  $('#cloudBox').style.display=settings.cloud.enabled?'':'none';
  $('#setWhisper').value=settings.whisper||'';
  $('#settingsModal').hidden=false;
});
$('#setTemp').addEventListener('input',function(){$('#tempVal').textContent=this.value;});
$('#setCloud').addEventListener('change',function(){$('#cloudBox').style.display=this.checked?'':'none';});
$('#saveSettingsBtn').addEventListener('click',function(){
  var url=$('#setUrl').value.trim()||'http://localhost:11434';
  if(!/^https?:\/\//.test(url))url='http://'+url;
  settings.ollamaUrl=url;
  settings.systemPrompt=$('#setSys').value.trim()||DEFAULT_SYS;
  settings.temp=parseFloat($('#setTemp').value)||0.7;
  settings.tools=$('#setTools').checked;
  settings.cloud.enabled=$('#setCloud').checked;
  var cb=$('#setCBase').value.trim()||'https://openrouter.ai/v1';
  if(!/^https:\/\//.test(cb))cb='https://'+cb;
  settings.cloud.base=cb.replace(/\/+$/,'');
  settings.cloud.key=$('#setCKey').value.trim();
  settings.cloud.model=$('#setCModel').value.trim();
  settings.whisper=$('#setWhisper').value.trim()||'';
  saveLS('arena.settings',settings);
  $('#settingsModal').hidden=true;
  updateToolsChip();updateArenaChip();loadModels();
  toast('&#9989; Pengaturan tersimpan');
});

/* tutup modal: tombol & klik area gelap & Esc */
document.querySelectorAll('.overlay').forEach(function(ov){
  ov.addEventListener('click',function(e){if(e.target===ov)ov.hidden=true;});
  ov.querySelectorAll('[data-close]').forEach(function(b){
    b.addEventListener('click',function(){ov.hidden=true;});
  });
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape')document.querySelectorAll('.overlay').forEach(function(ov){ov.hidden=true;});
});

/* aksi di dalam pesan: salin kode / salin pesan / detail tool */
msgBox.addEventListener('click',function(e){
  var pb=e.target.closest('.pickbtn');
  if(pb){
    var wm=pb.closest('.msg');var mm=wm&&wm.__arena;
    if(mm){mm.verdict={pick:+pb.getAttribute('data-pick'),judge:'',reason:'Dipilih manual oleh Anda.',manual:true};
      mm.judging=false;mm.done=true;paintArena(wm,mm);saveLS('arena.chats',chats);syncServer();renderSide();toast('&#128077; Jawaban dipilih');}
    return;
  }
  var ah=e.target.closest('.ac-head');
  if(ah&&!e.target.closest('.pickbtn')){
    var bd=ah.parentElement.querySelector('.ac-body');
    if(bd)bd.hidden=!bd.hidden;return;
  }
  var cc=e.target.closest('.copycode');
  if(cc){
    var code=cc.closest('.codeblock').querySelector('code').textContent;
    copyText(code);return;
  }
  var cm=e.target.closest('.copymsg');
  if(cm){
    var node=cm.closest('.msg').querySelector('.md');
    copyText(node.innerText);return;
  }
  var sm=e.target.closest('.speakmsg');
  if(sm){
    if(window.speechSynthesis&&speechSynthesis.speaking){speechSynthesis.cancel();return;}
    var mnode=sm.closest('.msg').querySelector('.md');
    speakText(mnode?mnode.innerText:'');return;
  }
  var tg=e.target.closest('.ev-toggle');
  if(tg){
    var det=tg.closest('.ev').querySelector('.ev-det');
    det.hidden=!det.hidden;
    tg.textContent=det.hidden?'detail':'sembunyikan';
  }
});
function copyText(t){
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(t).then(function(){toast('&#128203; Tersalin');},
      function(){toast('Gagal menyalin');});
  }else{
    var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);
    ta.select();try{document.execCommand('copy');toast('&#128203; Tersalin');}catch(e){}
    document.body.removeChild(ta);
  }
}

/* ================= init ================= */
bootHistory();
updateToolsChip();updateArenaChip();applyTheme();setSendState();
loadModels();refreshFiles();
autoGrow();input.focus();
</script>
</body>
</html>
"""

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main():
    global PLUGINS
    os.makedirs(WORKSPACE, exist_ok=True)
    PLUGINS = _load_plugins()
    storage.init(DB_PATH, VALKEY_URL)
    readme = os.path.join(WORKSPACE, "BACA-SAYA.txt")
    if not os.path.exists(readme):
        try:
            with open(readme, "w", encoding="utf-8") as fh:
                fh.write(
                    "Folder workspace untuk Kilat AI\n"
                    "=================================\n\n"
                    "File-file yang dibuat oleh AI akan tersimpan di sini.\n"
                    "Anda juga bisa memindahkan file Anda sendiri ke folder ini,\n"
                    "lalu meminta AI untuk membacanya (\"baca file ...\").\n"
                )
        except OSError:
            pass

    srv = None
    port = PORT
    for cand in range(PORT, PORT + 10):
        try:
            srv = ThreadingHTTPServer((HOST, cand), Handler)
            port = cand
            break
        except OSError:
            continue
    if srv is None:
        print("ERROR: port %d-%d semuanya terpakai. Tutup aplikasi lain," % (PORT, PORT + 9))
        print("atau jalankan dengan: python app.py --port 9090")
        sys.exit(1)

    url = "http://localhost:%d" % port
    print("=" * 52)
    print("  K I L A T   A I")
    print("  Asisten AI agentic - 100% di komputer Anda")
    print("=" * 52)
    print("  Buka di browser : %s" % url)
    print("  Server Ollama   : %s" % DEFAULT_OLLAMA)
    if EMBED_KEY:
        print("  Kunci embed     : AKTIF (%d karakter)" % len(EMBED_KEY))
    else:
        print("  Kunci embed     : nonaktif (opsional - lihat PANDUAN.md)")
    print("  Folder workspace: %s" % WORKSPACE)
    print("  Database SQLite : %s" % storage.DB_PATH)
    print("  Valkey          : %s" % ("terhubung - cache & antrean event aktif" if storage.valkey_ok() else "tidak aktif (opsional) - lihat PANDUAN.md"))
    print("  Plugin integrasi: %d aktif%s" % (
        len(PLUGINS),
        (" (" + ", ".join(p["file"] for p in PLUGINS) + ")") if PLUGINS else "",
    ))
    if os.path.isfile(KNOWLEDGE_FILE):
        print("  PENGETAHUAN.md  : aktif (konteks aplikasi disisipkan)")
    if WHISPER_URL:
        print("  Whisper (suara) : %s" % WHISPER_URL)
    print("  Tekan Ctrl+C untuk berhenti")
    print()

    if not NO_OPEN and HOST in ("127.0.0.1", "localhost", "0.0.0.0", ""):
        try:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nSampai jumpa! Kilat AI berhenti.")


if __name__ == "__main__":
    if "--port" in sys.argv:
        try:
            PORT = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass
    main()
