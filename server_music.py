"""
Xiaozhi YouTube Music Server (Hỗ trợ chạy Local & Cloud Render.com)
Tự động nhận diện Cookie để vượt qua tường lửa bot của YouTube trên Cloud.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import uvicorn
import socket
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


def setup_cookie_file():
    """Tự động kiểm tra và thiết lập file cookie nếu chạy trên Cloud"""
    # 1. Nếu có biến môi trường YOUTUBE_COOKIES (khuyên dùng trên Render)
    cookie_env = os.environ.get("YOUTUBE_COOKIES")
    if cookie_env:
        cookie_path = "/tmp/youtube_cookies.txt"
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_env)
        print("[+] Đã nạp YouTube Cookie từ biến môi trường YOUTUBE_COOKIES!")
        return cookie_path

    # 2. Nếu có file cookies.txt trong cùng thư mục
    local_cookie = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(local_cookie):
        print(f"[+] Đã tìm thấy file cookie tại: {local_cookie}")
        return local_cookie

    print("[!] Không tìm thấy cookie. Chạy chế độ không đăng nhập (có thể bị YouTube chặn trên Cloud).")
    return None


COOKIE_FILE = setup_cookie_file()

# Cấu hình yt-dlp tối ưu
YDL_OPTS_SEARCH = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "mweb"]
        }
    }
}
if COOKIE_FILE:
    YDL_OPTS_SEARCH["cookiefile"] = COOKIE_FILE

YDL_OPTS_STREAM = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "mweb"]
        }
    }
}
if COOKIE_FILE:
    YDL_OPTS_STREAM["cookiefile"] = COOKIE_FILE


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
    cookie_status = "🟢 Đã nạp Cookie (Vượt bot check OK)" if COOKIE_FILE else "🟡 Chưa có Cookie (Khuyên dùng trên Cloud)"
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
            .status-box {{ background: #334155; padding: 10px; border-radius: 8px; font-size: 0.9em; margin: 15px 0; color: #cbd5e1; }}
            input {{ padding: 12px; width: 65%; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 1em; }}
            button {{ padding: 12px 20px; border-radius: 6px; border: none; background: #38bdf8; color: #0f172a; font-weight: bold; cursor: pointer; }}
            button:hover {{ background: #7dd3fc; }}
            #results {{ margin-top: 20px; text-align: left; }}
            .song-item {{ background: #334155; padding: 12px; margin-bottom: 8px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }}
            audio {{ width: 100%; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🎵 Xiaozhi YouTube Music Server</h1>
            <p style="color: #94a3b8;">Hỗ trợ phát nhạc YouTube cho trợ lý AI Xiaozhi</p>
            
            <div class="status-box">
                Trạng thái: <strong>{cookie_status}</strong>
            </div>

            <div style="margin-top: 25px;">
                <input type="text" id="keyword" placeholder="Nhập tên bài hát..." value="Lạc trôi">
                <button onclick="searchSong()">Tìm & Nghe thử</button>
            </div>

            <div id="loading" style="display:none; margin-top:15px; color:#38bdf8;">Đang tìm kiếm bài hát...</div>
            <div id="results"></div>
            <audio id="audioPlayer" controls style="display:none;"></audio>
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
                    
                    const items = json.data?.items || [];
                    if (items.length === 0) {{
                        document.getElementById('results').innerHTML = '<p>Không tìm thấy bài hát nào.</p>';
                        return;
                    }}

                    let html = '';
                    items.forEach(item => {{
                        html += `
                        <div class="song-item">
                            <div>
                                <strong>${{item.title}}</strong><br>
                                <small style="color:#94a3b8;">${{item.artistsNames}}</small>
                            </div>
                            <button onclick="playSong('${{item.encodeId}}')">▶ Phát</button>
                        </div>`;
                    }});
                    document.getElementById('results').innerHTML = html;
                }} catch (e) {{
                    document.getElementById('loading').style.display = 'none';
                    alert('Lỗi: ' + e);
                }}
            }}

            function playSong(id) {{
                const player = document.getElementById('audioPlayer');
                player.src = `/api/song/stream?id=${{id}}`;
                player.style.display = 'block';
                player.play();
            }}
        </script>
    </body>
    </html>
    """


@app.get("/health")
def health_check():
    return {"status": "ok", "has_cookie": bool(COOKIE_FILE)}


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
def stream_song(id: str):
    """Lấy link stream audio trực tiếp từ YouTube và chuyển hướng ESP32 tới phát"""
    try:
        url = f"https://www.youtube.com/watch?v={id}"
        with yt_dlp.YoutubeDL(YDL_OPTS_STREAM) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info.get("url")
            if not audio_url:
                raise HTTPException(status_code=404, detail="Không tìm thấy luồng âm thanh")
            
            # Chuyển hướng 302 trực tiếp tới luồng audio của YouTube
            return RedirectResponse(url=audio_url, status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    # Tự động nhận diện port trên Render ($PORT) hoặc mặc định 8000
    port = int(os.environ.get("PORT", 8000))
    ip = get_local_ip()
    print("\n" + "=" * 65)
    print("   XIAOZHI YOUTUBE MUSIC SERVER ĐANG KHỞI ĐỘNG")
    print("=" * 65)
    print(f"[*] Port: {port}")
    print(f"[*] Local IP: http://{ip}:{port}")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
