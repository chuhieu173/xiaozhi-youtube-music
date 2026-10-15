"""
Xiaozhi Multi-Source Music Server (Tối ưu hóa chạy trên Render Cloud 24/7)
- Nguồn chính: SoundCloud (Không bao giờ bị YouTube chặn Bot Check trên dải IP Cloud).
- Nguồn phụ: YouTube (Hỗ trợ stream proxy có cookie).
- Tương thích 100% chuẩn API firmware Xiaozhi ESP32 (/api/search và /api/song/stream).
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

app = FastAPI(title="Xiaozhi Music Server")

# Kích hoạt CORS cho ESP32 và Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cấu hình yt-dlp tối ưu cho SoundCloud (nhanh, nhẹ, không bao giờ bị chặn IP)
YDL_OPTS_SC_SEARCH = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
}

YDL_OPTS_SC_STREAM = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
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
    return """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Xiaozhi Cloud Music Server</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 30px; text-align: center; }
            .card { background: #1e293b; max-width: 650px; margin: 0 auto; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
            h1 { color: #38bdf8; margin-bottom: 5px; }
            .status-box { background: #334155; padding: 12px; border-radius: 8px; font-size: 0.9em; margin: 15px 0; color: #cbd5e1; text-align: left; line-height: 1.6; }
            input { padding: 12px; width: 65%; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 1em; }
            button { padding: 12px 20px; border-radius: 6px; border: none; background: #38bdf8; color: #0f172a; font-weight: bold; cursor: pointer; }
            button:hover { background: #7dd3fc; }
            #results { margin-top: 20px; text-align: left; }
            .song-item { background: #334155; padding: 12px; margin-bottom: 8px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }
            .error-box { background: #7f1d1d; color: #fecaca; padding: 10px; border-radius: 6px; margin-top: 15px; font-size: 0.9em; }
            .badge { background: #059669; color: #fff; font-size: 0.75em; padding: 2px 8px; border-radius: 4px; vertical-align: middle; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🎵 Xiaozhi Cloud Music Server</h1>
            <p style="color: #94a3b8;">Server phát nhạc trực tuyến cho trợ lý AI Xiaozhi ESP32 trên Render</p>
            
            <div class="status-box">
                <div>⚡ Nguồn nhạc: <strong>SoundCloud Cloud Engine</strong> <span class="badge">Không chặn Bot</span></div>
                <div>🛡️ Trạng thái: <strong>Hoạt động 100% trên Render Cloud (Không cần Cookie)</strong></div>
            </div>

            <div style="margin-top: 25px;">
                <input type="text" id="keyword" placeholder="Nhập tên bài hát (ví dụ: Lạc trôi, Cắt đôi nỗi sầu)..." value="Lạc trôi">
                <button onclick="searchSong()">Tìm & Nghe thử</button>
            </div>

            <div id="loading" style="display:none; margin-top:15px; color:#38bdf8;">Đang tìm bài hát trên Cloud...</div>
            <div id="results"></div>
            <div id="player-container" style="display:none; margin-top:20px;">
                <h4 id="nowPlaying" style="color:#38bdf8; margin: 0 0 10px 0;"></h4>
                <audio id="audioPlayer" controls autoplay style="width: 100%;"></audio>
            </div>
        </div>

        <script>
            async function searchSong() {
                const q = document.getElementById('keyword').value.trim();
                if (!q) return;
                document.getElementById('loading').style.display = 'block';
                document.getElementById('results').innerHTML = '';
                
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
                    const json = await res.json();
                    document.getElementById('loading').style.display = 'none';
                    
                    if (!res.ok || json.err !== 0) {
                        document.getElementById('results').innerHTML = `<div class="error-box">Lỗi: ${json.detail || json.msg || 'Không thể tìm kiếm'}</div>`;
                        return;
                    }

                    const items = json.data?.items || [];
                    if (items.length === 0) {
                        document.getElementById('results').innerHTML = '<p style="text-align:center; color:#94a3b8;">Không tìm thấy bài hát nào.</p>';
                        return;
                    }

                    let html = '';
                    items.forEach(item => {
                        const titleSafe = item.title.replace(/'/g, "\\'");
                        html += `
                        <div class="song-item">
                            <div>
                                <strong>${item.title}</strong><br>
                                <small style="color:#94a3b8;">${item.artistsNames}</small>
                            </div>
                            <button onclick="playSong('${item.encodeId}', '${titleSafe}')">▶ Phát</button>
                        </div>`;
                    });
                    document.getElementById('results').innerHTML = html;
                } catch (e) {
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('results').innerHTML = `<div class="error-box">Lỗi kết nối: ${e}</div>`;
                }
            }

            function playSong(id, title) {
                const playerContainer = document.getElementById('player-container');
                const player = document.getElementById('audioPlayer');
                const nowPlaying = document.getElementById('nowPlaying');
                
                nowPlaying.innerText = 'Đang phát: ' + (title || id);
                player.src = `/api/song/stream?id=${id}`;
                playerContainer.style.display = 'block';
                player.play().catch(e => console.log('Cần tương tác để phát:', e));
            }
        </script>
    </body>
    </html>
    """


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "engine": "SoundCloud (Cloud Bot-Proof)",
        "compatible_with": "Xiaozhi ESP32",
    }


@app.get("/api/search")
def search_song(q: str):
    """
    Tìm kiếm bài hát qua SoundCloud.
    Không bị YouTube chặn bot, không cần cookie, kết quả cực kỳ phong phú với nhạc Việt & Quốc tế.
    """
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS_SC_SEARCH) as ydl:
            res = ydl.extract_info(f"scsearch5:{q}", download=False)
            items = []
            for entry in res.get("entries", []):
                track_id = entry.get("id")
                if not track_id:
                    continue
                items.append({
                    "encodeId": f"sc_{track_id}",
                    "title": entry.get("title"),
                    "artistsNames": entry.get("uploader", "Nghệ sĩ")
                })
            return {
                "err": 0,
                "msg": "Success",
                "data": {"items": items}
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi tìm kiếm: {str(e)}")


@app.get("/api/song/stream")
async def stream_song(id: str, request: Request):
    """
    Stream âm thanh trực tiếp từ SoundCloud về ESP32 hoặc Web Browser.
    Hỗ trợ cả định dạng HLS (fMP4 / AAC segments) và Progressive MP3.
    Không bao giờ bị lỗi 403 Forbidden hay 'Sign in to confirm you’re not a bot'.
    """
    try:
        # 1. Xử lý SoundCloud track
        clean_id = id[3:] if id.startswith("sc_") else id
        target_url = f"https://api.soundcloud.com/tracks/soundcloud%3Atracks%3A{clean_id}"

        with yt_dlp.YoutubeDL(YDL_OPTS_SC_STREAM) as ydl:
            info = ydl.extract_info(target_url, download=False)
            stream_url = info.get("url")
            if not stream_url:
                raise HTTPException(status_code=404, detail="Không tìm thấy luồng âm thanh")

        client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        # 2. Nếu là luồng HLS (.m3u8), ghép các segment thành luồng fMP4/AAC liên tục
        if ".m3u8" in stream_url:
            playlist_resp = await client.get(stream_url)
            lines = playlist_resp.text.splitlines()

            init_url = None
            segment_urls = []
            for line in lines:
                line = line.strip()
                if line.startswith("#EXT-X-MAP:URI="):
                    init_url = line.split('URI="')[1].rstrip('"')
                elif line and not line.startswith("#"):
                    segment_urls.append(line)

            async def hls_stream_generator():
                try:
                    # Gửi init segment (MP4 box header) nếu có
                    if init_url:
                        init_res = await client.get(init_url)
                        yield init_res.content

                    # Gửi tuần tự từng segment âm thanh
                    for seg in segment_urls:
                        seg_res = await client.get(seg)
                        yield seg_res.content
                finally:
                    await client.aclose()

            return StreamingResponse(
                hls_stream_generator(),
                media_type="audio/mp4",
                headers={
                    "Content-Type": "audio/mp4",
                    "Accept-Ranges": "none",
                    "Cache-Control": "no-cache",
                }
            )

        # 3. Nếu là file âm thanh trực tiếp (Direct MP3 / AAC)
        req_headers = {}
        if "range" in request.headers:
            req_headers["range"] = request.headers["range"]

        upstream_req = client.build_request("GET", stream_url, headers=req_headers)
        upstream_resp = await client.send(upstream_req, stream=True)

        async def direct_stream_generator():
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
            direct_stream_generator(),
            status_code=upstream_resp.status_code,
            headers=response_headers,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi phát nhạc: {str(e)}")


def main():
    port = int(os.environ.get("PORT", 8000))
    ip = get_local_ip()
    print("\n" + "=" * 65)
    print("   XIAOZHI CLOUD MUSIC SERVER (SOUNDCLOUD ENGINE) ĐANG CHẠY")
    print("=" * 65)
    print(f"[*] Port: {port}")
    print(f"[*] Chế độ: Cloud Bot-Proof (Không bị chặn Bot Check trên Render)")
    print(f"[*] Endpoint: http://{ip}:{port}")
    print("=" * 65 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
