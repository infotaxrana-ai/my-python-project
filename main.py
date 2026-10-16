import os
import json
import asyncio
import urllib.request
import urllib.parse
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Ultra Fast")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0NTE3MywiZXhwIjoxODIzNzAyNzczfQ.aTyC69_Edssdtzus-lyAGjFwfRDD55_9hQUu0t9oxo-TjU7e5TA_DHHXm3DnnGUuF8ek6A5hs2OGUSoDD19Z1A"

# ইনভিডিয়াস ও অন্যান্য নির্ভরযোগ্য পাবলিক ইনস্ট্যান্স তালিকা
INVIDIOUS_INSTANCES = [
    "https://inv.riverside.rocks",
    "https://invidious.nerdvpn.de",
    "https://vid.puppethead.one",
    "https://invidious.flokinet.to"
]

def get_youtube_audio_url(song_name: str) -> str:
    encoded_query = urllib.parse.quote(song_name)
    
    for instance in INVIDIOUS_INSTANCES:
        try:
            # ১. গান দিয়ে ইউটিউব ভিডিও আইডি সার্চ করা
            search_url = f"{instance}/api/v1/search?q={encoded_query}&type=video"
            req = urllib.request.Request(
                search_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                search_data = json.loads(response.read().decode())
                if search_data and len(search_data) > 0:
                    video_id = search_data[0].get("videoId")
                    if video_id:
                        # ২. ভিডিওর মেটাডাটা থেকে ডাইরেক্ট অডিও স্ট্রিম লিংক বের করা
                        video_url = f"{instance}/api/v1/videos/{video_id}"
                        req_video = urllib.request.Request(
                            video_url,
                            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                        )
                        with urllib.request.urlopen(req_video, timeout=4) as vid_resp:
                            vid_data = json.loads(vid_resp.read().decode())
                            adaptive_formats = vid_data.get("adaptiveFormats", [])
                            # সরাসরি অডিও ফরমেট নির্বাচন
                            audio_streams = [f for f in adaptive_formats if f.get("type", "").startswith("audio/")]
                            if audio_streams:
                                # সেরা বিটরেটের অডিও লিংক নির্বাচন
                                audio_streams.sort(key=lambda x: int(x.get("bitrate", 0)), reverse=True)
                                direct_audio_url = audio_streams[0].get("url")
                                print(f"Successfully fetched audio from {instance}: {direct_audio_url}")
                                return direct_audio_url
        except Exception as e:
            print(f"Error fetching from instance {instance}: {e}")
            continue

    print("All extraction methods failed.")
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
                                "capabilities": {
                                    "tools": {}
                                },
                                "serverInfo": {
                                    "name": "xiaozhi-youtube-mcp",
                                    "version": "3.0.0"
                                }
                            }
                        }
                        await ws.send(json.dumps(response))

                    elif method == "ping":
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {}
                        }
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
                            audio_url = get_youtube_audio_url(song_name)
                            
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
    return {"status": "Xiaozhi YouTube Audio MCP Server Ultra Fast is running"}

@app.get("/api/get-audio-url")
def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}
