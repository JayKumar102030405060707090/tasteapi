# app.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import yt_dlp
from youtubesearchpython import VideosSearch
import uvicorn

app = FastAPI(title="YouTube API Backend", version="1.0")

# Allow all CORS (you can restrict later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper: yt-dlp extraction
def extract_info(url, download=False):
    ydl_opts = {"quiet": True, "skip_download": not download}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download)

# 1. /youtube?query=...&video=true/false
@app.get("/youtube")
def youtube_search(query: str, video: bool = False):
    try:
        search = VideosSearch(query, limit=10)
        results = search.result()["result"]
        filtered = []
        for item in results:
            if video and item.get("type") != "video":
                continue
            filtered.append({
                "title": item["title"],
                "link": item["link"],
                "duration": item.get("duration"),
                "thumbnail": item["thumbnails"][0]["url"],
                "videoId": item["id"]
            })
        return {"results": filtered}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 2. /details?link=...
@app.get("/details")
def youtube_details(link: str):
    try:
        info = extract_info(link)
        return {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "videoId": info.get("id")
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 3. /track?link=...
@app.get("/track")
def youtube_track(link: str):
    try:
        info = extract_info(link)
        return {
            "title": info.get("title"),
            "link": link,
            "thumbnail": info.get("thumbnail"),
            "videoId": info.get("id")
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 4. /formats?link=...
@app.get("/formats")
def youtube_formats(link: str):
    try:
        info = extract_info(link)
        formats = []
        for f in info.get("formats", []):
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("resolution"),
                "filesize": f.get("filesize"),
                "format_note": f.get("format_note"),
                "acodec": f.get("acodec"),
                "vcodec": f.get("vcodec"),
                "url": f.get("url")
            })
        return {"formats": formats}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 5. /playlist?link=...&limit=...
@app.get("/playlist")
def youtube_playlist(link: str, limit: Optional[int] = 100):
    try:
        info = extract_info(link)
        entries = info.get("entries", [])
        videos = []
        for idx, entry in enumerate(entries):
            if idx >= limit:
                break
            videos.append({
                "title": entry.get("title"),
                "videoId": entry.get("id"),
                "link": f"https://youtu.be/{entry.get('id')}",
                "thumbnail": entry.get("thumbnail")
            })
        return {"videos": videos}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 6. /download/audio?link=...
@app.get("/download/audio")
def download_audio(link: str):
    try:
        info = extract_info(link)
        best_audio = None
        for f in info['formats']:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                if not best_audio or (f.get('abr', 0) > best_audio.get('abr', 0)):
                    best_audio = f
        if not best_audio:
            return JSONResponse(status_code=404, content={"error": "No audio format found"})
        return {"download_url": best_audio['url']}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 7. /download/video?link=...
@app.get("/download/video")
def download_video(link: str):
    try:
        info = extract_info(link)
        best_video = info['url'] if 'url' in info else None
        if best_video:
            return {"download_url": best_video}
        # fallback: get best progressive format
        best = None
        for f in info['formats']:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                if not best or (f.get('height', 0) > best.get('height', 0)):
                    best = f
        if not best:
            return JSONResponse(status_code=404, content={"error": "No video format found"})
        return {"download_url": best['url']}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 8. /download/custom?link=...&format_id=...&title=...
@app.get("/download/custom")
def download_custom(link: str, format_id: str, title: Optional[str] = None):
    try:
        info = extract_info(link)
        target_format = next((f for f in info['formats'] if f['format_id'] == format_id), None)
        if not target_format:
            return JSONResponse(status_code=404, content={"error": "Format ID not found"})
        return {
            "title": title if title else info.get('title'),
            "download_url": target_format['url']
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 9. /search?query=...
@app.get("/search")
def search_videos(query: str):
    try:
        search = VideosSearch(query, limit=10)
        results = search.result()["result"]
        data = []
        for item in results:
            data.append({
                "title": item["title"],
                "link": item["link"],
                "duration": item.get("duration"),
                "thumbnail": item["thumbnails"][0]["url"],
                "videoId": item["id"]
            })
        return {"results": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# 10. /slider?query=...&index=...
@app.get("/slider")
def slider_result(query: str, index: int = 0):
    try:
        search = VideosSearch(query, limit=10)
        results = search.result()["result"]
        if index < 0 or index >= len(results):
            return JSONResponse(status_code=400, content={"error": "Invalid index"})
        item = results[index]
        return {
            "title": item["title"],
            "link": item["link"],
            "duration": item.get("duration"),
            "thumbnail": item["thumbnails"][0]["url"],
            "videoId": item["id"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
