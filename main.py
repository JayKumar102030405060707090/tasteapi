# main.py

import asyncio
import os
import re
from typing import Union, Optional, List
import yt_dlp
import httpx
import aioredis

from fastapi import FastAPI, Depends, HTTPException, status, Query, Form
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from youtubesearchpython.__future__ import VideosSearch

app = FastAPI(title="YouTube API Ultimate", version="1.0")

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Redis connection
redis = aioredis.from_url("redis://localhost", decode_responses=True)

# Hardcoded API Key
API_KEY = "JAYDIP"

# RESPONSE FORMAT keys
RESPONSE_KEYS = ["id", "title", "duration", "link", "channel", "views", "thumbnail", "stream_url", "stream_type"]


def auth(api_key: str = Query(...)):
    if api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def response_builder(data: dict) -> dict:
    """Ensure all required keys, null if missing"""
    return {k: data.get(k, None) for k in RESPONSE_KEYS}


def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    output = out.decode().strip()
    error = err.decode().strip()
    if "unavailable videos are hidden" in error.lower():
        return output
    return output if not err else error


async def get_stream_url(query, video=False):
    # Dummy external API placeholder
    api_url = "https://example.com/api/stream"  # Replace this with actual external stream API
    params = {"query": query, "video": video, "api_key": API_KEY}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(api_url, params=params)
            if response.status_code != 200:
                return ""
            info = response.json()
            return info.get("stream_url")
    except Exception:
        return ""


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.regex = r"(?:youtube\.com|youtu\.be)"

    def clean_link(self, link: str) -> str:
        return link.split("&")[0]

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return True if re.search(self.regex, link) else False

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = self.clean_link(link)
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result.get("title")
            duration_min = result.get("duration")
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result.get("id")
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = self.clean_link(link)
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return {
                "title": result.get("title"),
                "link": result.get("link"),
                "vidid": result.get("id"),
                "duration_min": result.get("duration"),
                "thumb": result["thumbnails"][0]["url"].split("?")[0],
            }

    async def playlist(self, link: str, limit: int, user_id: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        link = self.clean_link(link)
        playlist = await shell_cmd(f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}")
        return [x for x in playlist.split("\n") if x]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = self.clean_link(link)
        loop = asyncio.get_running_loop()

        def extract_formats():
            formats_available = []
            ydl = yt_dlp.YoutubeDL({"quiet": True})
            r = ydl.extract_info(link, download=False)
            for fmt in r.get("formats", []):
                if "dash" not in str(fmt.get("format", "")).lower():
                    formats_available.append({
                        "format": fmt.get("format"),
                        "filesize": fmt.get("filesize"),
                        "format_id": fmt.get("format_id"),
                        "ext": fmt.get("ext"),
                        "format_note": fmt.get("format_note"),
                        "yturl": link
                    })
            return formats_available

        return await loop.run_in_executor(None, extract_formats)

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = self.clean_link(link)
        results = (await VideosSearch(link, limit=10).next()).get("result")
        r = results[query_type]
        return r.get("title"), r.get("duration"), r["thumbnails"][0]["url"].split("?")[0], r.get("id")

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        link = self.clean_link(link)
        return await get_stream_url(link, True)

    async def download(self, link: str, video: Union[bool, str], videoid: Union[bool, str], songaudio: Union[bool, str], songvideo: Union[bool, str], format_id: Union[str, None], title: Union[str, None]):
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        def song_video_dl():
            formats = f"{format_id}+140"
            outtmpl = f"downloads/{title}"
            yt_opts = {"format": formats, "outtmpl": outtmpl, "quiet": True, "merge_output_format": "mp4"}
            yt_dlp.YoutubeDL(yt_opts).download([link])
            return f"{outtmpl}.mp4"

        def song_audio_dl():
            outtmpl = f"downloads/{title}.%(ext)s"
            yt_opts = {
                "format": format_id,
                "outtmpl": outtmpl,
                "quiet": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            }
            yt_dlp.YoutubeDL(yt_opts).download([link])
            return f"downloads/{title}.mp3"

        if songvideo:
            return await loop.run_in_executor(None, song_video_dl)
        elif songaudio:
            return await loop.run_in_executor(None, song_audio_dl)
        else:
            return await get_stream_url(link, bool(video))


ytapi = YouTubeAPI()

# ----------------- ROUTES ------------------

@app.post("/stream")
@limiter.limit("100/minute")
async def stream(query: str = Form(...), video: bool = Form(False), api_key: str = Depends(auth)):
    cache_key = f"stream:{query}:{video}"
    cached = await redis.get(cache_key)
    if cached:
        return {"stream_url": cached}
    url = await get_stream_url(query, video)
    await redis.setex(cache_key, 21600, url)
    return {"stream_url": url}


@app.get("/details")
@limiter.limit("100/minute")
async def details(link: str, videoid: Optional[Union[bool, str]] = None, api_key: str = Depends(auth)):
    title, dur, dur_sec, thumb, vidid = await ytapi.details(link, videoid)
    data = response_builder({
        "id": vidid, "title": title, "duration": dur_sec, "link": link, "channel": None,
        "views": None, "thumbnail": thumb, "stream_url": None, "stream_type": None
    })
    return JSONResponse(content=data)


@app.get("/track")
@limiter.limit("100/minute")
async def track(link: str, videoid: Optional[Union[bool, str]] = None, api_key: str = Depends(auth)):
    info = await ytapi.track(link, videoid)
    data = response_builder({
        "id": info.get("vidid"), "title": info.get("title"), "duration": int(time_to_seconds(info.get("duration_min"))) if info.get("duration_min") else 0,
        "link": info.get("link"), "channel": None, "views": None, "thumbnail": info.get("thumb"),
        "stream_url": None, "stream_type": None
    })
    return JSONResponse(content=data)


@app.get("/playlist")
@limiter.limit("100/minute")
async def playlist(link: str, limit: int, user_id: str, videoid: Optional[Union[bool, str]] = None, api_key: str = Depends(auth)):
    result = await ytapi.playlist(link, limit, user_id, videoid)
    return {"playlist": result}


@app.get("/formats")
@limiter.limit("100/minute")
async def formats(link: str, videoid: Optional[Union[bool, str]] = None, api_key: str = Depends(auth)):
    result = await ytapi.formats(link, videoid)
    return {"formats": result}


@app.get("/slider")
@limiter.limit("100/minute")
async def slider(link: str, query_type: int, videoid: Optional[Union[bool, str]] = None, api_key: str = Depends(auth)):
    title, dur, thumb, vidid = await ytapi.slider(link, query_type, videoid)
    data = response_builder({
        "id": vidid, "title": title, "duration": int(time_to_seconds(dur)) if dur else 0,
        "link": link, "channel": None, "views": None, "thumbnail": thumb,
        "stream_url": None, "stream_type": None
    })
    return JSONResponse(content=data)


@app.post("/download")
@limiter.limit("100/minute")
async def download(
    link: str = Form(...),
    video: bool = Form(False),
    videoid: Optional[Union[bool, str]] = Form(None),
    songaudio: Optional[Union[bool, str]] = Form(None),
    songvideo: Optional[Union[bool, str]] = Form(None),
    format_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    api_key: str = Depends(auth),
):
    path = await ytapi.download(link, video, videoid, songaudio, songvideo, format_id, title)
    return {"download_path": path}


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(content={"detail": "Rate limit exceeded"}, status_code=429)
