import os
import subprocess
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Xiaozhi YouTube Audio MCP")

# সার্ভার স্টার্ট হলে অটোমেটিক yt-dlp আপডেট করবে
@app.on_event("startup")
def startup_event():
    try:
        subprocess.run(["python", "-m", "pip", "install", "--upgrade", "yt-dlp"], check=True)
        print("yt-dlp version updated successfully!")
    except Exception as e:
        print(f"Failed to auto-update yt-dlp: {e}")

# Xiaozhi MCP Tool Definition
@app.get("/mcp/tools")
def get_tools():
    return {
        "tools": [
            {
                "name": "play_youtube_audio",
                "description": "Searches YouTube for a song and returns a direct audio stream URL for ESP32 playback.",
                "parameters": {
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

# অডিও ইউআরএল বের করার মূল লজিক
@app.get("/api/get-audio-url")
def get_audio_url(song_name: str = Query(..., description="Song name to search")):
    try:
        # yt-dlp কমান্ডের সাহায্যে ইউটিউব সার্চ করে ডাইরেক্ট অডিও স্ট্রিম ইউআরএল ফেচ করা
        cmd = [
            "yt-dlp",
            f"ytsearch1:{song_name}",
            "--format", "bestaudio/best",
            "--get-url",
            "--no-playlist"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stream_url = result.stdout.strip()

        if not stream_url:
            raise HTTPException(status_code=404, detail="No audio stream found")

        return {
            "status": "success",
            "song": song_name,
            "audio_url": stream_url
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"yt-dlp error: {e.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
