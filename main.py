import os
import json
import asyncio
import urllib.parse
import httpx
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Direct Stream")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0ODgwNiwiZXhwIjoxODIzNzA2NDA2fQ.xOjGHWuoBf6XWU6GtI-E5zqOuSORi0J4MRtS6EzIgQYX1vsoYA4IjfF2cX7WaVKA9vfprjRhkhcpgsXtfxeaaQ"

async def get_youtube_audio_url(song_name: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    encoded_song = urllib.parse.quote(song_name)
    
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers, verify=False) as client:
        # অত্যন্ত নির্ভরযোগ্য ব্যাকআপ পাবলিক এপিআই (Cobalt & InnerTube Direct Search)
        try:
            # ইউটিউব থেকে সরাসরি মিউজিক পেড রিকোয়েস্টের বিকল্প হিসেবে ইনোভেটিভ সার্চ API
            search_endpoint = f"https://vid.priv.au/api/v1/search?q={encoded_song}&type=video"
            resp = await client.get(search_endpoint)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    video_id = data[0].get("videoId")
                    if video_id:
                        # সরাসরি কোবাল্ট এপিআইতে পাঠিয়ে অডিও লিংক ফেচ করা
                        cobalt_payload = {
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "downloadMode": "audio",
                            "audioFormat": "mp3"
                        }
                        c_resp = await client.post("https://api.cobalt.tools/api/json", json=cobalt_payload)
                        if c_resp.status_code == 200:
                            c_data = c_resp.json()
                            direct_url = c_data.get("url")
                            if direct_url:
                                print(f"Successfully fetched audio via Cobalt: {direct_url}")
                                return direct_url
        except Exception as e:
            print(f"Primary fetch error: {e}")

        # ফলব্যাক হিসেবে আরেকটি বিশ্বস্ত ইনস্ট্যান্স
        try:
            fallback_url = f"https://invidious.projectsegfau.lt/api/v1/search?q={encoded_song}&type=video"
            resp = await client.get(fallback_url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    video_id = data[0].get("videoId")
                    if video_id:
                        stream_res = await client.get(f"https://invidious.projectsegfau.lt/api/v1/videos/{video_id}")
                        if stream_res.status_code == 200:
                            v_data = stream_res.json()
                            formats = v_data.get("adaptiveFormats", [])
                            audio_streams = [f for f in formats if f.get("type", "").startswith("audio/")]
                            if audio_streams:
                                audio_streams.sort(key=lambda x: int(x.get("bitrate", 0)), reverse=True)
                                direct_url = audio_streams[0].get("url")
                                if direct_url:
                                    print(f"Successfully fetched from fallback Invidious: {direct_url}")
                                    return direct_url
        except Exception as e:
            print(f"Fallback fetch error: {e}")

    print("All audio extraction attempts failed.")
    return ""

async def xiaozhi_mcp_client():
    while True:
        try:
            print("Connecting to Xiaozhi MCP WebSocket...")
            async with websockets.connect(XIAOZHI_MCP_WS_URL) as ws:
                print("Connected to Xiaozhi MCP Endpoint!")
                
                async for message in ws:
                    data = json.loads(message)
                    print("Received from Xiaozhi:", data)
                    
                    req_id = data.get("id")
                    method = data.get("method")

                    if method == "initialize":
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {"tools": {}},
                                "serverInfo": {"name": "xiaozhi-youtube-mcp", "version": "9.0.0"}
                            }
                        }
                        await ws.send(json.dumps(response))

                    elif method == "ping":
                        response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                        await ws.send(json.dumps(response))

                    elif method == "tools/list":
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "tools": [
                                    {
                                        "name": "play_youtube_audio",
                                        "description": "Searches YouTube for a song and returns a direct audio stream URL for ESP32 playback.",
                                        "inputSchema": {
                                            "type": "object",
                                            "properties": {
                                                "song_name": {
                                                    "type": "string",
                                                    "description": "The title or query of the song to search on YouTube"
                                                }
                                            },
                                            "required": ["song_name"]
                                        }
                                    }
                                ]
                            }
                        }
                        await ws.send(json.dumps(response))

                    elif method == "tools/call":
                        params = data.get("params", {})
                        tool_name = params.get("name")
                        args = params.get("arguments", {})

                        if tool_name == "play_youtube_audio":
                            song_name = args.get("song_name", "")
                            audio_url = await get_youtube_audio_url(song_name)
                            
                            response = {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": json.dumps({
                                                "status": "success" if audio_url else "failed",
                                                "song": song_name,
                                                "audio_url": audio_url
                                            })
                                        }
                                    ]
                                }
                            }
                            await ws.send(json.dumps(response))

        except Exception as e:
            print(f"WebSocket Connection Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(xiaozhi_mcp_client())

@app.get("/")
def home():
    return {"status": "Direct Stream Server running"}

@app.get("/api/get-audio-url")
async def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = await get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}