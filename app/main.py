# app/main.py
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Union, List, Dict, Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.agents.graph import build_workflow

DB_URI = os.getenv("DATABASE_URL", "postgresql://postgres:securepassword123@db:5432/nexusops")

workflow_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global workflow_app
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()
        
        raw_workflow = build_workflow()
        workflow_app = raw_workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["apply_fix"]
        )
        
        yield

app = FastAPI(title="NexusOps AI API", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    image_base64: Optional[str] = None

class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool

@app.post("/chat")
async def run_chat_agent(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    existing = await workflow_app.aget_state(config)

    if existing.values and existing.next:
        return {
            "status": "suspended_for_approval",
            "thread_id": req.thread_id,
            "next_node": existing.next,
            "snapshot": existing.values
        }

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

    result = await workflow_app.ainvoke(initial_input, config)
    state = await workflow_app.aget_state(config)

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
async def resume_with_approval(req: ApprovalRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    state = await workflow_app.aget_state(config)
    
    if not state.next:
        raise HTTPException(status_code=400, detail="No active paused thread found for this ID.")
        
    approval_val = "approved" if req.approved else "rejected"
    
    await workflow_app.aupdate_state(config, {"approval_status": approval_val})
    resumed_result = await workflow_app.ainvoke(None, config)
    
    return {
        "status": "resumed_and_completed",
        "approval_status": approval_val,
        "result": resumed_result
    }