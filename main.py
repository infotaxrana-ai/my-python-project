import os
import json
import asyncio
import subprocess
import urllib.request
import urllib.parse
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Pro Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# আপনার Xiaozhi MCP WebSocket Endpoint URL
XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SWQiOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjEzNDUxMywiZXhwIjoxODIzNjkyMTEzfQ.ZD3ndBqAPg5EMnmZ5CptHfOjS2rTTPlG-pBANnDKkQHa9o6EBKYrdvC3byMuodHQpLk_5eEaKJQ44mgPyl1A9A"

# yt-dlp অটো আপডেট ফাংশন
def update_yt_dlp():
    try:
        subprocess.run(["python", "-m", "pip", "install", "--upgrade", "yt-dlp"], check=True)
        print("yt-dlp updated successfully!")
    except Exception as e:
        print(f"Failed to auto-update yt-dlp: {e}")

# অল্টারনেটিভ ফলব্যাক মেথড: Piped API দিয়ে অডিও লিংক বের করা (যাতে Render আইপি ব্লক না খায়)
def get_audio_from_fallback_api(song_name: str) -> str:
    try:
        encoded_query = urllib.parse.quote(song_name)
        search_url = f"https://pipedapi.kavin.rocks/search?q={encoded_query}&filter=videos"
        
        req = urllib.request.Request(
            search_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            items = data.get("items", [])
            if items:
                # প্রথম ভিডিওর আইডি নেওয়া
                video_id = items[0].get("url", "").split("=")[-1]
                if video_id:
                    # স্ট্রিম এপিআই থেকে সরাসরি অডিও লিংক ফেচ করা
                    stream_url = f"https://pipedapi.kavin.rocks/streams/{video_id}"
                    req_stream = urllib.request.Request(
                        stream_url, 
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    )
                    with urllib.request.urlopen(req_stream, timeout=5) as stream_resp:
                        stream_data = json.loads(stream_resp.read().decode())
                        audio_streams = stream_data.get("audioStreams", [])
                        if audio_streams:
                            # সেরা অডিও ইউআরএল রিটার্ন করা
                            direct_url = audio_streams[0].get("url", "")
                            print(f"Successfully Fetched via Fallback API: {direct_url}")
                            return direct_url
    except Exception as e:
        print(f"Fallback API error: {e}")
    return ""

# ইউটিউব থেকে নিখুঁতভাবে অডিও স্ট্রিম ইউআরএল বের করার মূল ফাংশন (ডুয়েল প্রটেকশন সহ)
def get_youtube_audio_url(song_name: str) -> str:
    # প্রথমে yt-dlp দিয়ে চেষ্টা করা যাক
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch1:{song_name}",
            "--get-url",
            "--no-check-certificates",
            "--extractor-args", "youtube:player_client=android",
            "-f", "bestaudio/best",
            "--no-playlist"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        url = result.stdout.strip().split('\n')[0]
        if url and url.startswith("http"):
            print(f"Successfully Fetched via yt-dlp: {url}")
            return url
    except Exception as e:
        print(f"yt-dlp primary method failed: {e}. Switching to Fallback API...")

    # yt-dlp ফেইল করলে স্বয়ংক্রিয়ভাবে ফলব্যাক API কাজ করবে
    return get_audio_from_fallback_api(song_name)

# Xiaozhi MCP WebSocket Client Task
async def xiaozhi_mcp_client():
    while True:
        try:
            print("Connecting to Xiaozhi MCP WebSocket...")
            async with websockets.connect(XIAOZHI_MCP_WS_URL) as ws:
                print("Connected to Xiaozhi MCP Endpoint!")
                
                # মেসেজ রিসিভ এবং প্রসেস লুপ
                async for message in ws:
                    data = json.loads(message)
                    print("Received from Xiaozhi:", data)
                    
                    req_id = data.get("id")
                    method = data.get("method")

                    # ১. Initialize হ্যান্ডশেক
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
                                    "version": "2.0.0"
                                }
                            }
                        }
                        await ws.send(json.dumps(response))

                    # ২. Ping হ্যান্ডশেক
                    elif method == "ping":
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {}
                        }
                        await ws.send(json.dumps(response))

                    # ৩. Tools List রিকোয়েস্ট হ্যান্ডেল করা
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

                    # ৪. Tool Call (গান বাজানোর কমান্ড)
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
    # ব্যাকগ্রাউন্ডে WebSocket ক্লায়েন্ট চালু করা
    asyncio.create_task(xiaozhi_mcp_client())

@app.get("/")
def home():
    return {"status": "Xiaozhi YouTube Audio MCP Server Pro is running"}

# ম্যানুয়াল টেস্টের জন্য HTTP endpoint
@app.get("/api/get-audio-url")
def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}
