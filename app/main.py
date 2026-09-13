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
checkpointer_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global workflow_app, checkpointer_instance
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()
        checkpointer_instance = checkpointer
        
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

@app.get("/sessions")
async def list_sessions():
    sessions = ["ops-session-01"]
    try:
        if checkpointer_instance:
            checkpoint_tuples = [cp async for cp in checkpointer_instance.alist(None)]
            found_threads = list(set([
                cp.config["configurable"]["thread_id"] 
                for cp in checkpoint_tuples 
                if cp.config and "configurable" in cp.config and "thread_id" in cp.config["configurable"]
            ]))
            if found_threads:
                sessions = found_threads
    except Exception:
        pass
    return {"sessions": sessions}

@app.get("/history/{thread_id}")
async def get_session_history(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await workflow_app.aget_state(config)
        messages = []
        if state and state.values and "messages" in state.values:
            messages = state.values["messages"]
            
        return {
            "thread_id": thread_id,
            "messages": messages,
            "suspended": bool(state.next) if state and state.next else False,
            "next_node": state.next if state and state.next else None,
            "snapshot": state.values if state and state.values else {}
        }
    except Exception:
        return {
            "thread_id": thread_id,
            "messages": [],
            "suspended": False,
            "next_node": None,
            "snapshot": {}
        }

@app.delete("/sessions/{thread_id}")
async def delete_session(thread_id: str):
    try:
        # Native method if available in checkpointer version
        if hasattr(checkpointer_instance, "adelete_thread"):
            await checkpointer_instance.adelete_thread(thread_id)
        
        # Explicit connection cleanup to clear transaction state cache
        async with checkpointer_instance.conn.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s;", (thread_id,))
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s;", (thread_id,))
                await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s;", (thread_id,))
            await conn.commit()
            
        return {"status": "success", "deleted": thread_id}
    except Exception as e:
        try:
            async with checkpointer_instance.conn as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s;", (thread_id,))
                    await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s;", (thread_id,))
                    await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s;", (thread_id,))
                await conn.commit()
            return {"status": "success", "deleted": thread_id}
        except Exception as inner_e:
            raise HTTPException(status_code=500, detail=str(inner_e))

class RenameRequest(BaseModel):
    new_thread_id: str

@app.put("/sessions/{thread_id}")
async def rename_session(thread_id: str, req: RenameRequest):
    new_id = req.new_thread_id.strip()
    if not new_id:
        raise HTTPException(status_code=400, detail="New session name cannot be empty.")
    try:
        try:
            async with checkpointer_instance.conn.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("UPDATE checkpoint_writes SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                    await cur.execute("UPDATE checkpoints SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                    await cur.execute("UPDATE checkpoint_blobs SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                await conn.commit()
        except Exception:
            async with checkpointer_instance.conn as conn:
                async with conn.cursor() as cur:
                    await cur.execute("UPDATE checkpoint_writes SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                    await cur.execute("UPDATE checkpoints SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                    await cur.execute("UPDATE checkpoint_blobs SET thread_id = %s WHERE thread_id = %s;", (new_id, thread_id))
                await conn.commit()
        return {"status": "success", "old_id": thread_id, "new_id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    thread_id: str
    message: str
    image_base64: Optional[str] = None

class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool

@app.post("/chat")
async def run_chat_agent(req: ChatRequest):
    try:
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
    except Exception as e:
        print(f"Chat Execution Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/approve")
async def resume_with_approval(req: ApprovalRequest):
    try:
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
    except Exception as e:
        print(f"Approval Execution Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))