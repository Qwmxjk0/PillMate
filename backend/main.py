from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator
import uvicorn

app = FastAPI(
    title="PillMate Backend API",
    description="FastAPI backend with Server-Sent Events support",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "PillMate Backend API",
        "version": "1.0.0",
        "endpoints": {
            "sse": "/events",
            "docs": "/docs",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/events")
async def stream_events():
    """Server-Sent Events endpoint"""
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def event_stream() -> AsyncGenerator[str, None]:
    """Generate server-sent events"""
    counter = 0
    try:
        while True:
            # Create a sample event
            event_data = {
                "id": counter,
                "timestamp": datetime.now().isoformat(),
                "message": f"Event {counter}",
                "data": {
                    "counter": counter,
                    "random_value": counter * 2
                }
            }
            
            # Format as SSE
            event = f"id: {counter}\n"
            event += f"event: message\n"
            event += f"data: {json.dumps(event_data)}\n\n"
            
            yield event
            counter += 1
            
            # Wait before sending next event
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        # Client disconnected
        print("Client disconnected from SSE stream")
        raise

@app.get("/events/custom")
async def stream_custom_events(duration: int = 30, interval: float = 1.0):
    """Custom SSE endpoint with configurable duration and interval"""
    if duration > 300:  # Max 5 minutes
        raise HTTPException(status_code=400, detail="Duration cannot exceed 300 seconds")
    
    return StreamingResponse(
        custom_event_stream(duration, interval),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def custom_event_stream(duration: int, interval: float) -> AsyncGenerator[str, None]:
    """Generate custom server-sent events with specified duration and interval"""
    counter = 0
    start_time = datetime.now()
    
    try:
        while (datetime.now() - start_time).total_seconds() < duration:
            event_data = {
                "id": counter,
                "timestamp": datetime.now().isoformat(),
                "message": f"Custom event {counter}",
                "progress": min(100, (counter * 100) // (duration // int(interval))),
                "data": {
                    "counter": counter,
                    "elapsed_seconds": (datetime.now() - start_time).total_seconds(),
                    "remaining_seconds": duration - (datetime.now() - start_time).total_seconds()
                }
            }
            
            # Format as SSE
            event = f"id: {counter}\n"
            event += f"event: custom\n"
            event += f"data: {json.dumps(event_data)}\n\n"
            
            yield event
            counter += 1
            
            await asyncio.sleep(interval)
            
    except asyncio.CancelledError:
        print("Client disconnected from custom SSE stream")
        raise

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
