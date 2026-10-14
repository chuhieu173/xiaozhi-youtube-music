from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
import yt_dlp
import uvicorn

app = FastAPI(title="Xiaozhi YouTube Music Server")

YDL_OPTS_SEARCH = {
    "quiet": True,
    "skip_download": True,
    "extract_flat": True,
}

YDL_OPTS_STREAM = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
}

@app.get("/")
def home():
    return {"status": "ok", "message": "Xiaozhi YouTube Music Server is running!"}

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
            # 302 Redirect thẳng tới luồng audio của YouTube
            return RedirectResponse(url=audio_url, status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
