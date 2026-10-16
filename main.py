import os
import json
import asyncio
import urllib.parse
import httpx
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Multi Fallback")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0NjUzMCwiZXhwIjoxODIzNzA0MTMwfQ.Yr3F5jKJAQwhVE6O4ZtwYHdavTHT1cbWig9Bar2ZWh92TOo32061S-NVUT16NEQc1taT_jIS_eJEi84GjZMUDA"

async def get_youtube_audio_url(song_name: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    encoded_song = urllib.parse.quote(song_name)
    
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers, verify=False) as client:
        
        # 1. Invidious Active Instances
        invidious_instances = [
            "https://invidious.nerdvpn.de",
            "https://inv.tux.pizza",
            "https://invidious.projectsegfau.lt",
            "https://invidious.privacydev.net"
        ]
        
        for instance in invidious_instances:
            try:
                search_url = f"{instance}/api/v1/search?q={encoded_song}&type=video"
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        video_id = data[0].get("videoId")
                        if video_id:
                            video_resp = await client.get(f"{instance}/api/v1/videos/{video_id}")
                            if video_resp.status_code == 200:
                                v_data = video_resp.json()
                                adaptive_formats = v_data.get("adaptiveFormats", [])
                                audio_streams = [f for f in adaptive_formats if f.get("type", "").startswith("audio/")]
                                if audio_streams:
                                    audio_streams.sort(key=lambda x: int(x.get("bitrate", 0)), reverse=True)
                                    direct_url = audio_streams[0].get("url")
                                    if direct_url:
                                        print(f"Successfully fetched audio from Invidious ({instance}): {direct_url}")
                                        return direct_url
            except Exception as e:
                print(f"Invidious instance error ({instance}): {e}")
                continue

        # 2. Piped Active Instances
        piped_instances = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.leptons.xyz",
            "https://api.piped.privacydev.net"
        ]
        
        for base_url in piped_instances:
            try:
                search_url = f"{base_url}/search?q={encoded_song}&filter=videos"
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    if items:
                        video_url_path = items[0].get("url", "")
                        video_id = video_url_path.split("=")[-1] if "=" in video_url_path else ""
                        
                        if video_id:
                            stream_resp = await client.get(f"{base_url}/streams/{video_id}")
                            if stream_resp.status_code == 200:
                                stream_data = stream_resp.json()
                                audio_streams = stream_data.get("audioStreams", [])
                                if audio_streams:
                                    direct_url = audio_streams[0].get("url", "")
                                    if direct_url:
                                        print(f"Successfully fetched audio from Piped ({base_url}): {direct_url}")
                                        return direct_url
            except Exception as e:
                print(f"Piped instance error ({base_url}): {e}")
                continue

    print("All extraction attempts failed.")
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
                                "serverInfo": {"name": "xiaozhi-youtube-mcp", "version": "8.0.0"}
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
    return {"status": "Server running with multi-instance fallback"}

@app.get("/api/get-audio-url")
async def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = await get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}