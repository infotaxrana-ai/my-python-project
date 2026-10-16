import os
import json
import asyncio
import httpx
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Async HTTPX")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOjJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0NTE3MywiZXhwIjoxODIzNzAyNzczfQ.aTyC69_Edssdtzus-lyAGjFwfRDD55_9hQUu0t9oxo-TjU7e5TA_DHHXm3DnnGUuF8ek6A5hs2OGUSoDD19Z1A"

# নির্ভরযোগ্য এপিআই ক্লাস্টার
SEARCH_APIS = [
    "https://api.piped.privacydev.net",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.tokhmi.xyz"
]

async def get_youtube_audio_url(song_name: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
        # ১. Piped API ক্লাস্টার দিয়ে অডিও খোঁজা
        for base_url in SEARCH_APIS:
            try:
                search_url = f"{base_url}/search?q={httpx.URL(song_name).raw_path.decode()}&filter=videos"
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
                                    print(f"Successfully fetched audio from {base_url}: {direct_url}")
                                    return direct_url
            except Exception as e:
                print(f"Error connecting to {base_url}: {e}")
                continue

        # ২. ব্যাকআপ Cobalt API চেষ্টা
        try:
            cobalt_payload = {
                "url": f"https://www.youtube.com/watch?v=search?q={song_name}",
                "downloadMode": "audio"
            }
            c_resp = await client.post("https://api.cobalt.tools/api/json", json=cobalt_payload)
            if c_resp.status_code == 200:
                c_data = c_resp.json()
                url = c_data.get("url")
                if url:
                    print(f"Successfully fetched audio via Cobalt: {url}")
                    return url
        except Exception as e:
            print(f"Cobalt backup failed: {e}")

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
                                "serverInfo": {"name": "xiaozhi-youtube-mcp", "version": "6.0.0"}
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
    return {"status": "Xiaozhi Async Server is running"}

@app.get("/api/get-audio-url")
async def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = await get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}