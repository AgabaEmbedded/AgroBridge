from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/")
async def handle_voicebip_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = await request.form()
        
    event_type = data.get("event") or data.get("event_type")
    print(f"\n--- Received Event: {event_type} ---")
    print(data)
    
    # 1. Handle call initiation or completion status events
    if event_type in ["call.initiated", "call.completed", "call.barge_in"]:
        return JSONResponse({"status": "received"})
        
    # 2. Handle conversational turns (when the user speaks into the phone)
    if event_type == "turn":
        farmer_speech = data.get("transcription", "")
        print(f"🌾 Farmer said: '{farmer_speech}'")
        
        # Here is where you can later plug in OpenAI! 
        # For now, let's reply with a dynamic response acknowledging what they said.
        ai_reply = f"Hello! I heard you say: {farmer_speech}. How can Farm Direct help your crops today?"
        
        # Voicebip BYOM expects the response text under 'response' (and sometimes 'text')
        return JSONResponse({
            "response": ai_reply,
            "text": ai_reply
        })
        
    # Fallback default response
    return JSONResponse({
        "response": "Hello from Farm Direct! How can I help you today?"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)