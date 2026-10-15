"""
Xiaozhi YouTube Music Server (Hỗ trợ chạy Local & Cloud Render.com)
Tự động Stream Proxy luồng âm thanh để tránh lỗi 403 Forbidden do YouTube kiểm tra lệch IP.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import uvicorn
import httpx
import socket
import os
import sys

app = FastAPI(title="Xiaozhi YouTube Music Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def setup_cookie_file():
    cookie_env = os.environ.get("YOUTUBE_COOKIES")
    if cookie_env:
        cookie_path = "/tmp/youtube_cookies.txt"
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_env)
        return cookie_path
    local_cookie = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(local_cookie):
        return local_cookie
    return None

COOKIE_FILE = setup_cookie_file()

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
    "format": "bestaudio[ext=m4a]/bestaudio/best",
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

@app.get("/", response_class=HTMLResponse)
def index_page():
    cookie_status = "🟢 Đã nạp Cookie (Vượt bot check OK)" if COOKIE_FILE else "🟡 Chưa có Cookie"
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
            <p style="color: #94a3b8;">Hỗ trợ phát nhạc YouTube cho trợ lý AI Xiaozhi ESP32</p>
            <div class="status-box">Trạng thái: <strong>{cookie_status}</strong> | Chế độ: <strong>Stream Proxy (Chống 403)</strong></div>
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
                            <div><strong>${{item.title}}</strong><br><small style="color:#94a3b8;">${{item.artistsNames}}</small></div>
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
            return {"err": 0, "msg": "Success", "data": {"items": items}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/song/stream")
async def stream_song(id: str, request: Request):
    """Stream âm thanh trực tiếp từ YouTube qua Render về Client (tránh lỗi 403 do lệch IP)"""
    try:
        url = f"https://www.youtube.com/watch?v={id}"
        with yt_dlp.YoutubeDL(YDL_OPTS_STREAM) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info.get("url")
            if not audio_url:
                raise HTTPException(status_code=404, detail="Không tìm thấy luồng âm thanh")

        client = httpx.AsyncClient(timeout=60.0)
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
        raise HTTPException(status_code=500, detail=str(e))

def main():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
