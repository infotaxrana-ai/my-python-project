import os
import json
import asyncio
import urllib.request
import urllib.parse
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Cobalt Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0NTE3MywiZXhwIjoxODIzNzAyNzczfQ.aTyC69_Edssdtzus-lyAGjFwfRDD55_9hQUu0t9oxo-TjU7e5TA_DHHXm3DnnGUuF8ek6A5hs2OGUSoDD19Z1A"

def get_youtube_audio_url(song_name: str) -> str:
    try:
        # ১. ইনভিডিয়াস সার্চ সার্ভারের মাধ্যমে ভিডিও আইডি বের করা
        encoded_query = urllib.parse.quote(song_name)
        search_url = f"https://invidious.nerdvpn.de/api/v1/search?q={encoded_query}&type=video"
        
        req_search = urllib.request.Request(
            search_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        
        video_id = ""
        with urllib.request.urlopen(req_search, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data and len(data) > 0:
                video_id = data[0].get("videoId", "")

        if not video_id:
            # সার্চ ব্যাকআপ (Piped search)
            piped_url = f"https://pipedapi.kavin.rocks/search?q={encoded_query}&filter=videos"
            req_piped = urllib.request.Request(piped_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_piped, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("items", [])
                if items:
                    video_id = items[0].get("url", "").split("=")[-1]

        if video_id:
            # ২. Cobalt API ব্যবহার করে সরাসরি অডিও স্ট্রিম লিংক তৈরি
            yt_video_url = f"https://www.youtube.com/watch?v={video_id}"
            cobalt_url = "https://api.cobalt.tools/api/json"
            
            payload = json.dumps({
                "url": yt_video_url,
                "downloadMode": "audio",
                "audioFormat": "mp3"
            }).encode('utf-8')

            req_cobalt = urllib.request.Request(
                cobalt_url,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0'
                },
                method='POST'
            )

            with urllib.request.urlopen(req_cobalt, timeout=8) as resp:
                result = json.loads(resp.read().decode())
                direct_url = result.get("url", "")
                if direct_url:
                    print(f"Successfully fetched Cobalt Audio URL: {direct_url}")
                    return direct_url

    except Exception as e:
        print(f"Cobalt / Search extraction error: {e}")

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
                                "serverInfo": {"name": "xiaozhi-youtube-mcp", "version": "5.0.0"}
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
    return {"status": "Cobalt MCP Server is running"}

@app.get("/api/get-audio-url")
def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}