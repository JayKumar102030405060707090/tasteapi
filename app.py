import asyncio
import uuid
import time
from fastapi import FastAPI, Request, Response, HTTPException, Query
import yt_dlp
import httpx

app = FastAPI()
stream_cache = {}

# --- अपनी API key यहाँ डालो ---
API_KEYS = {"abc123": True}  # ← अपनी key डालो

class YouTubeAPI:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }

    async def search_youtube(self, query: str):
        """yt-dlp का उपयोग करके सर्च करें"""
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'force_generic_extractor': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = await asyncio.to_thread(ydl.extract_info, f"ytsearch:{query}", download=False)
                return info['entries'][0]['url']
            except Exception as e:
                print(f"Search error: {e}")
                return None

    async def extract_info(self, url: str, video: bool = False):
        """वीडियो इन्फो एक्सट्रैक्ट करें"""
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if 'entries' in info:
                    info = info['entries'][0]
                
                stream_id = str(uuid.uuid4())
                
                # --- Safe stream selection ---
                if video:
                    actual_url = next(
                        (f['url'] for f in info['formats'] if f.get('vcodec') != 'none' and 'url' in f),
                        None
                    )
                else:
                    actual_url = next(
                        (f['url'] for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and 'url' in f),
                        None
                    )

                if not actual_url:
                    raise HTTPException(status_code=500, detail="No suitable stream found")

                # --- Cache store ---
                stream_cache[stream_id] = {
                    'url': actual_url,
                    'expires': time.time() + 3600  # 1 hour expiry
                }
                
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'link': info.get('webpage_url'),
                    'thumbnail': info.get('thumbnail'),
                    'stream_url': f"/stream/{stream_id}",
                    'stream_type': 'Video' if video else 'Audio'
                }

            except Exception as e:
                print(f"Extraction error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

youtube_api = YouTubeAPI()

@app.get("/youtube")
async def youtube_endpoint(
    query: str = Query(...),
    video: bool = Query(False),
    api_key: str = Query(...)
):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    if not ("youtube.com" in query or "youtu.be" in query):
        query = await youtube_api.search_youtube(query)
        if not query:
            raise HTTPException(status_code=404, detail="Video not found")
    
    return await youtube_api.extract_info(query, video)

@app.get("/stream/{stream_id}")
async def stream_proxy(
    stream_id: str,
    request: Request,
    api_key: str = Query(...)
):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    if stream_id not in stream_cache:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    stream_info = stream_cache[stream_id]
    
    if time.time() > stream_info['expires']:
        del stream_cache[stream_id]
        raise HTTPException(status_code=410, detail="Stream expired")
    
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() in ['range', 'accept']
    }
    
    async with httpx.AsyncClient() as client:
        async with client.stream('GET', stream_info['url'], headers=headers) as response:
            return Response(
                content=response.iter_bytes(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get('content-type')
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1470)
