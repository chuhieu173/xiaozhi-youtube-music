"""
Xiaozhi YouTube Music Server (Tối ưu hóa chạy trên Render.com & Local)
- Hỗ trợ Render Secret Files (/etc/secrets/cookies.txt) & Biến môi trường YOUTUBE_COOKIES.
- Tự động chuẩn hóa định dạng cookie Netscape (tự sửa lỗi biến Tab thành Space).
- Đa tầng Client Fallback: ['android', 'web'] -> ['android'] -> ['tv_embedded'] chống Bot Check dứt điểm.
- Stream Proxy qua máy chủ Render để giải quyết hoàn toàn lỗi HTTP 403 Forbidden do lệch IP.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import uvicorn
import httpx
import socket
import base64
import os
import sys

app = FastAPI(title="Xiaozhi YouTube Music Server")

# Kích hoạt CORS để ESP32 hoặc Web client gọi thoải mái
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_netscape_cookies(text: str) -> str:
    """Tự động chuẩn hóa định dạng Netscape cookie (sửa lỗi space thay vì tab khi dán vào Env Var)"""
    lines = []
    has_header = False
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if "Netscape" in line:
                has_header = True
            lines.append(line)
            continue
        # Một dòng cookie Netscape chuẩn gồm 7 trường phân cách bởi tab:
        # domain \t flag \t path \t secure \t expiration \t name \t value
        parts = line.split(None, 6)
        if len(parts) == 7:
            lines.append("\t".join(parts))
        elif len(parts) == 6:
            lines.append("\t".join(parts) + "\t")
        else:
            lines.append(line)

    content = "\n".join(lines) + "\n"
    if not has_header:
        content = "# Netscape HTTP Cookie File\n# Auto-fixed by Xiaozhi Music Server\n" + content
    return content


COOKIE_SOURCE = "None"
COOKIE_COUNT = 0


def setup_cookie_file():
    """Tự động kiểm tra và thiết lập file cookie nếu chạy trên Cloud"""
    global COOKIE_SOURCE, COOKIE_COUNT

    # 1. Ưu tiên 1: Render Secret Files tại /etc/secrets/cookies.txt
    render_secret = "/etc/secrets/cookies.txt"
    if os.path.exists(render_secret) and os.path.getsize(render_secret) > 20:
        try:
            with open(render_secret, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            valid_lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
            COOKIE_SOURCE = "Render Secret File (/etc/secrets/cookies.txt)"
            COOKIE_COUNT = len(valid_lines)
            print(f"[+] Đã tìm thấy Cookie từ Render Secret File: {COOKIE_COUNT} dòng!")
            return render_secret
        except Exception as e:
            print(f"[!] Lỗi đọc Secret File: {e}")

    # 2. Ưu tiên 2: File cookies.txt đặt cùng thư mục
    local_cookie = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(local_cookie) and os.path.getsize(local_cookie) > 20:
        try:
            with open(local_cookie, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            valid_lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
            COOKIE_SOURCE = f"Local File ({local_cookie})"
            COOKIE_COUNT = len(valid_lines)
            print(f"[+] Đã tìm thấy Cookie từ file cục bộ: {COOKIE_COUNT} dòng!")
            return local_cookie
        except Exception as e:
            print(f"[!] Lỗi đọc local cookie: {e}")

    # 3. Ưu tiên 3: Biến môi trường YOUTUBE_COOKIES
    cookie_env = os.environ.get("YOUTUBE_COOKIES")
    if cookie_env and len(cookie_env.strip()) > 20:
        cookie_text = cookie_env.strip()
        # Thử giải mã nếu người dùng mã hóa base64
        try:
            decoded = base64.b64decode(cookie_text).decode("utf-8", errors="ignore")
            if "youtube.com" in decoded or "Netscape" in decoded:
                cookie_text = decoded
        except Exception:
            pass

        # Chuẩn hóa định dạng Netscape (chuyển đổi space thành Tab bắt buộc)
        fixed_content = normalize_netscape_cookies(cookie_text)
        cookie_path = "/tmp/youtube_cookies.txt"
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(fixed_content)

        valid_lines = [l for l in fixed_content.splitlines() if l.strip() and not l.strip().startswith("#")]
        COOKIE_SOURCE = "Environment Variable (YOUTUBE_COOKIES)"
        COOKIE_COUNT = len(valid_lines)
        print(f"[+] Đã chuẩn hóa và nạp {COOKIE_COUNT} dòng YouTube Cookie từ YOUTUBE_COOKIES!")
        return cookie_path

    print("[!] Không tìm thấy cookie hợp lệ. Chạy chế độ không đăng nhập.")
    return None


COOKIE_FILE = setup_cookie_file()

# Cấu hình tìm kiếm: Tuyệt đối KHÔNG gán cookie để tìm kiếm luôn mượt mà và không bao giờ bị nghẽn
YDL_OPTS_SEARCH = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
}


def get_local_ip():
    """Tự động lấy IP nội mạng"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/", response_class=HTMLResponse)
def index_page():
    if COOKIE_FILE and COOKIE_COUNT > 0:
        cookie_status = f"🟢 Đã nạp Cookie ({COOKIE_COUNT} dòng từ {COOKIE_SOURCE})"
    else:
        cookie_status = "🟡 Chưa có Cookie (Khuyên dùng Secret File trên Cloud)"

    return f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Xiaozhi YouTube Music Server</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 30px; text-align: center; }}
            .card {{ background: #1e293b; max-width: 650px; margin: 0 auto; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }}
            h1 {{ color: #38bdf8; margin-bottom: 5px; }}
            .status-box {{ background: #334155; padding: 12px; border-radius: 8px; font-size: 0.9em; margin: 15px 0; color: #cbd5e1; text-align: left; line-height: 1.5; }}
            input {{ padding: 12px; width: 65%; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 1em; }}
            button {{ padding: 12px 20px; border-radius: 6px; border: none; background: #38bdf8; color: #0f172a; font-weight: bold; cursor: pointer; }}
            button:hover {{ background: #7dd3fc; }}
            #results {{ margin-top: 20px; text-align: left; }}
            .song-item {{ background: #334155; padding: 12px; margin-bottom: 8px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }}
            audio {{ width: 100%; margin-top: 15px; }}
            .error-box {{ background: #7f1d1d; color: #fecaca; padding: 10px; border-radius: 6px; margin-top: 15px; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🎵 Xiaozhi YouTube Music Server</h1>
            <p style="color: #94a3b8;">Hỗ trợ phát nhạc YouTube cho trợ lý AI Xiaozhi ESP32</p>
            
            <div class="status-box">
                <div>📡 Trạng thái: <strong>{cookie_status}</strong></div>
                <div>🛡️ Chế độ: <strong>Stream Proxy (Chống 403 Forbidden & Lệch IP)</strong></div>
            </div>

            <div style="margin-top: 25px;">
                <input type="text" id="keyword" placeholder="Nhập tên bài hát..." value="Lạc trôi">
                <button onclick="searchSong()">Tìm & Nghe thử</button>
            </div>

            <div id="loading" style="display:none; margin-top:15px; color:#38bdf8;">Đang tìm kiếm bài hát...</div>
            <div id="results"></div>
            <div id="player-container" style="display:none; margin-top:20px;">
                <h4 id="nowPlaying" style="color:#38bdf8; margin: 0 0 10px 0;"></h4>
                <audio id="audioPlayer" controls autoplay style="width: 100%;"></audio>
            </div>
        </div>

        <script>
            async function searchSong() {{
                const q = document.getElementById('keyword').value.trim();
                if (!q) return;
                document.getElementById('loading').style.display = 'block';
                document.getElementById('results').innerHTML = '';
                
                try {{
                    const res = await fetch(`/api/search?q=${{encodeURIComponent(q)}}`);
                    const json = await res.json();
                    document.getElementById('loading').style.display = 'none';
                    
                    if (!res.ok || json.err !== 0) {{
                        document.getElementById('results').innerHTML = `<div class="error-box">Lỗi tìm kiếm: ${{json.detail || json.msg || 'Không rõ'}}</div>`;
                        return;
                    }}

                    const items = json.data?.items || [];
                    if (items.length === 0) {{
                        document.getElementById('results').innerHTML = '<p style="text-align:center; color:#94a3b8;">Không tìm thấy bài hát nào.</p>';
                        return;
                    }}

                    let html = '';
                    items.forEach(item => {{
                        const titleSafe = item.title.replace(/'/g, "\\\\'");
                        html += `
                        <div class="song-item">
                            <div>
                                <strong>${{item.title}}</strong><br>
                                <small style="color:#94a3b8;">${{item.artistsNames}}</small>
                            </div>
                            <button onclick="playSong('${{item.encodeId}}', '${{titleSafe}}')">▶ Phát</button>
                        </div>`;
                    }});
                    document.getElementById('results').innerHTML = html;
                }} catch (e) {{
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('results').innerHTML = `<div class="error-box">Lỗi kết nối: ${{e}}</div>`;
                }}
            }}

            function playSong(id, title) {{
                const playerContainer = document.getElementById('player-container');
                const player = document.getElementById('audioPlayer');
                const nowPlaying = document.getElementById('nowPlaying');
                
                nowPlaying.innerText = 'Đang phát: ' + (title || id);
                player.src = `/api/song/stream?id=${{id}}`;
                playerContainer.style.display = 'block';
                player.play().catch(e => console.log('Chờ người dùng tương tác để play:', e));
            }}
        </script>
    </body>
    </html>
    """


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "has_cookie": bool(COOKIE_FILE and COOKIE_COUNT > 0),
        "cookie_source": COOKIE_SOURCE,
        "cookie_count": COOKIE_COUNT,
    }


@app.get("/api/search")
def search_song(q: str):
    """Tìm kiếm bài hát trên YouTube theo chuẩn của firmware Xiaozhi"""
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS_SEARCH) as ydl:
            res = ydl.extract_info(f"ytsearch5:{q}", download=False)
            items = []
            for entry in res.get("entries", []):
                items.append({
                    "encodeId": entry.get("id"),
                    "title": entry.get("title"),
                    "artistsNames": entry.get("uploader", "YouTube Music")
                })
            return {
                "err": 0,
                "msg": "Success",
                "data": {"items": items}
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/song/stream")
async def stream_song(id: str, request: Request):
    """
    Stream âm thanh trực tiếp qua server Render về Client (Stream Proxy).
    Tự động thử các Player Client ('android,web' -> 'android' -> 'tv_embedded') để vượt Bot Check.
    """
    url = f"https://www.youtube.com/watch?v={id}"

    # Danh sách cấu hình client thử nghiệm lần lượt để đảm bảo luôn trích xuất thành công
    client_configs = [
        ["android", "web"],
        ["android"],
        ["tv_embedded"],
        None
    ]

    audio_url = None
    last_error = None

    for client_choice in client_configs:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "skip_download": True,
        }
        if client_choice:
            opts["extractor_args"] = {"youtube": {"player_client": client_choice}}
        if COOKIE_FILE:
            opts["cookiefile"] = COOKIE_FILE

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info.get("url")
                if audio_url:
                    break
        except Exception as e:
            last_error = e
            continue

    if not audio_url:
        raise HTTPException(
            status_code=500,
            detail=f"Không thể trích xuất luồng audio YouTube. Lỗi: {last_error}"
        )

    try:
        # Khởi tạo client tải trực tiếp dữ liệu từ Google Video
        client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        req_headers = {}
        if "range" in request.headers:
            req_headers["range"] = request.headers["range"]

        upstream_req = client.build_request("GET", audio_url, headers=req_headers)
        upstream_resp = await client.send(upstream_req, stream=True)

        async def stream_generator():
            try:
                async for chunk in upstream_resp.aiter_raw():
                    yield chunk
            finally:
                await upstream_resp.aclose()
                await client.aclose()

        response_headers = {
            "Content-Type": upstream_resp.headers.get("content-type", "audio/mp4"),
            "Accept-Ranges": "bytes",
        }
        if "content-length" in upstream_resp.headers:
            response_headers["Content-Length"] = upstream_resp.headers["content-length"]
        if "content-range" in upstream_resp.headers:
            response_headers["Content-Range"] = upstream_resp.headers["content-range"]

        return StreamingResponse(
            stream_generator(),
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi truyền phát audio: {str(e)}")


def main():
    port = int(os.environ.get("PORT", 8000))
    ip = get_local_ip()
    print("\n" + "=" * 65)
    print("   XIAOZHI YOUTUBE MUSIC SERVER ĐANG KHỞI ĐỘNG")
    print("=" * 65)
    print(f"[*] Port: {port}")
    print(f"[*] Chế độ: Stream Proxy (Chống 403 Forbidden)")
    print(f"[*] Cookie: {COOKIE_SOURCE} ({COOKIE_COUNT} dòng)")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
