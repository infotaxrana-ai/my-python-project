import os
import json
import asyncio
import urllib.parse
import httpx
import websockets
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Xiaozhi YouTube Audio MCP Server - Direct Stable")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

XIAOZHI_MCP_WS_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwMzIwNzcsImFnZW50SOjI0OTc5NTgsImVuZHBvaW50SWQiOiJhZ2VudF8yNDk3OTU4IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5MjE0ODgwNiwiZXhwIjoxODIzNzA2NDA2fQ.xOjGHWuoBf6XWU6GtI-E5zqOuSORi0J4MRtS6EzIgQYX1vsoYA4IjfF2cX7WaVKA9vfprjRhkhcpgsXtfxeaaQ"

async def get_youtube_audio_url(song_name: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    encoded_song = urllib.parse.quote(song_name)
    
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers, verify=False) as client:
        # বিকল্প এবং সবচেয়ে স্টেবল পাবলিক সার্চ মাধ্যম ব্যবহার করে ভিডিও আইডি বের করা
        video_id = ""
        try:
            # NewPipe Extractor compatible public API endpoint
            search_resp = await client.get(f"https://pipedapi.kavin.rocks/search?q={encoded_song}&filter=videos")
            if search_resp.status_code == 200:
                data = search_resp.json()
                items = data.get("items", [])
                if items:
                    url_path = items[0].get("url", "")
                    if "=" in url_path:
                        video_id = url_path.split("=")[-1]
        except Exception as e:
            print(f"Search API error: {e}")

        # যদি প্রথম সার্চ ফেইল করে, সরাসরি Cobalt API কে কোয়েরি পাঠানো (এটি নিজেই ইউটিউব থেকে গান প্রসেস করে নেয়)
        if not video_id:
            try:
                cobalt_payload = {
                    "url": f"https://www.youtube.com/results?search_query={encoded_song}",
                    "downloadMode": "audio",
                    "audioFormat": "mp3"
                }
                c_resp = await client.post("https://api.cobalt.tools/api/json", json=cobalt_payload)
                if c_resp.status_code == 200:
                    c_data = c_resp.json()
                    direct_url = c_data.get("url")
                    if direct_url:
                        print(f"Successfully fetched via direct Cobalt search: {direct_url}")
                        return direct_url
            except Exception as e:
                print(f"Cobalt direct search error: {e}")

        # যদি ভিডিও আইডি পাওয়া যায়, তবে Cobalt এপিআই ব্যবহার করে সরাসরি অডিও লিংক নেওয়া
        if video_id:
            try:
                yt_link = f"https://www.youtube.com/watch?v={video_id}"
                cobalt_payload = {
                    "url": yt_link,
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
                print(f"Cobalt fetch error: {e}")

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
                                "serverInfo": {"name": "xiaozhi-youtube-mcp", "version": "11.0.0"}
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
    return {"status": "Direct Stable Server running"}

@app.get("/api/get-audio-url")
async def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    url = await get_youtube_audio_url(song_name)
    return {"song": song_name, "audio_url": url}
