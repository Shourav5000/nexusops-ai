from dotenv import load_dotenv
load_dotenv()  # Automatically loads ANTHROPIC_API_KEY from your .env file

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Union, List, Dict, Any
from app.agents.graph import build_workflow

app = FastAPI(title="NexusOps AI API", version="1.0.0")
workflow_app = build_workflow()

# Mount static folder so the frontend dashboard is accessible
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    image_base64: Optional[str] = None  # Multimodal support for screenshots and error logs

class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool

@app.post("/chat")
def run_chat_agent(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    existing = workflow_app.get_state(config)

    # Same thread_id already waiting on HITL — do not append another copy of the message
    if existing.values and existing.next:
        return {
            "status": "suspended_for_approval",
            "thread_id": req.thread_id,
            "next_node": existing.next,
            "snapshot": existing.values
        }

    # Handle multimodal input structure if an image was attached
    message_content: Union[str, List[Dict[Any, Any]]] = req.message
    if req.image_base64:
        message_content = [
            {"type": "text", "text": req.message},
            {"type": "image_url", "image_url": {"url": req.image_base64}}
        ]

    initial_input = {
        "messages": [{"role": "user", "content": message_content}],
        "approval_status": "none",
        "requires_approval": False
    }

    result = workflow_app.invoke(initial_input, config)
    state = workflow_app.get_state(config)

    if state.next:
        return {
            "status": "suspended_for_approval",
            "thread_id": req.thread_id,
            "next_node": state.next,
            "snapshot": state.values
        }

    return {
        "status": "completed",
        "thread_id": req.thread_id,
        "result": result
    }

@app.post("/approve")
def resume_with_approval(req: ApprovalRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    state = workflow_app.get_state(config)
    
    if not state.next:
        raise HTTPException(status_code=400, detail="No active paused thread found for this ID.")
        
    approval_val = "approved" if req.approved else "rejected"
    
    # Update state with human feedback and resume execution past the interrupt point
    workflow_app.update_state(config, {"approval_status": approval_val})
    resumed_result = workflow_app.invoke(None, config)
    
    return {
        "status": "resumed_and_completed",
        "approval_status": approval_val,
        "result": resumed_result
    }