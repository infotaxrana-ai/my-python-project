import os
import json
import asyncio
import subprocess
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apnar Xiaozhi MCP WebSocket Endpoint URL
XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjEzNDUxMywiZXhwIjoxODIzNjkyMTEzfQ.ZD3ndBqAPg5EMnmZ5CptHfOjS2rTTPlG-pBANnDKkQHa9o6EBKYrdvC3byMuodHQpLk_5eEaKJQ44mgPyl1A9A"

# yt-dlp oto update function
def update_yt_dlp():
    try:
        subprocess.run(["python", "-m", "pip", "install", "--upgrade", "yt-dlp"], check=True)
        print("yt-dlp updated successfully!")
    except Exception as e:
        print(f"Failed to auto-update yt-dlp: {e}")

# YouTube theke audio stream URL ber korar function
def get_youtube_audio_url(song_name: str) -> str:
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch1:{song_name}",
            "--format", "bestaudio/best",
            "--get-url",
            "--no-playlist"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        url = result.stdout.strip()
        return url
    except Exception as e:
        print(f"yt-dlp error: {e}")
        return ""

# Xiaozhi MCP WebSocket Client Task
async def xiaozhi_mcp_client():
    while True:
        try:
            print("Connecting to Xiaozhi MCP WebSocket...")
            async with websockets.connect(XIAOZHI_MCP_WS_URL) as ws:
                print("Connected to Xiaozhi MCP Endpoint!")
                
                # Message receive and process loop
                async for message in ws:
                    data = json.loads(message)
                    print("Received from Xiaozhi:", data)
                    
                    req_id = data.get("id")
                    method = data.get("method")

                    # 1. Initialize Handshake Handle
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
                                    "version": "1.0.0"
                                }
                            }
                        }
                        await ws.send(json.dumps(response))

                    # 2. Ping Pong Handle
                    elif method == "ping":
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {}
                        }
                        await ws.send(json.dumps(response))

                    # 3. Tools List Request Handle
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

                    # 4. Tool Call (Gan baajar command)
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
    update_yt_dlp()
    # Background e WebSocket client chalu kora
    asyncio.create_task(xiaozhi_mcp_client())

@app.get("/")
def home():
    return {"status": "Xiaozhi MCP Server is running"}

# Manual test er jonno HTTP endpoint
@app.get("/api/get-audio-url")
def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}
