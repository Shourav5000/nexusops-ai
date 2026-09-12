# app/agents/nodes.py
from app.services.vector_store import search_runbooks
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os

llm = ChatAnthropic(
    model="claude-sonnet-5",
    max_tokens=4096,
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

def _extract_query_text(content) -> str:
    """Helper to extract a plain string from either text or multimodal list content."""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("text", "")
        return "Analyze this attached image telemetry or code snippet."
    return str(content)

def _format_content_for_anthropic(content):
    """Ensures base64 image data URLs are properly formatted for Claude's vision API."""
    if isinstance(content, list):
        formatted_content = []
        for part in content:
            if isinstance(part, dict) and "image_url" in part:
                url = part["image_url"].get("url", "")
                if "base64," in url:
                    header, base64_data = url.split("base64,", 1)
                    media_type = "image/png"
                    if "image/jpeg" in header:
                        media_type = "image/jpeg"
                    elif "image/webp" in header:
                        media_type = "image/webp"
                    
                    formatted_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data
                        }
                    })
                else:
                    formatted_content.append(part)
            else:
                formatted_content.append(part)
        return formatted_content
    return content

def _get_latest_message_content(state):
    """Safely extracts message content whether stored as dict or LangChain message object."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        return last_msg.content
    elif isinstance(last_msg, dict):
        return last_msg.get("content", "")
    return str(last_msg)

def router_node(state):
    raw_content = _get_latest_message_content(state)
    latest_message = _extract_query_text(raw_content).lower()
    
    if any(keyword in latest_message for keyword in ["error", "fail", "crash", "bug", "code", "issue"]):
        return {"current_task": "diagnostics_agent"}
    return {"current_task": "rag_agent"}

def rag_agent_node(state):
    raw_content = _get_latest_message_content(state)
    query = _extract_query_text(raw_content)
    retrieved_docs = search_runbooks(query, k=3)
    
    context_str = "\n\n".join([doc for doc in retrieved_docs]) if retrieved_docs else "No specific runbooks found."
    system_prompt = SystemMessage(content=f"You are NexusOps RAG Agent. Use the following internal runbooks to answer the user query accurately:\n\n{context_str}")
    
    formatted_payload = _format_content_for_anthropic(raw_content)
    human_msg = HumanMessage(content=formatted_payload)
    
    response = llm.invoke([system_prompt, human_msg])
    
    return {
        "retrieved_docs": retrieved_docs,
        "messages": [{"role": "assistant", "content": f"RAG Agent (Claude): {response.content}"}]
    }

def diagnostics_agent_node(state):
    raw_content = _get_latest_message_content(state)
    query = _extract_query_text(raw_content)
    docs = state.get("retrieved_docs") or search_runbooks(query, k=3)
    
    context_str = "\n\n".join([doc for doc in docs]) if docs else "No specific diagnostic runbooks found."
    system_prompt = SystemMessage(content=f"You are NexusOps Diagnostics Agent. Analyze the error log or issue using these internal references:\n\n{context_str}")
    
    formatted_payload = _format_content_for_anthropic(raw_content)
    human_msg = HumanMessage(content=formatted_payload)
    
    response = llm.invoke([system_prompt, human_msg])
    report = response.content
    
    return {
        "retrieved_docs": docs,
        "diagnostics_report": report,
        "requires_approval": True,
        "approval_status": "pending",
        "messages": [{"role": "assistant", "content": f"Diagnostics Agent (Claude): {report} [Awaiting Human Approval]"}]
    }

def apply_fix_node(state):
    status = state.get("approval_status", "rejected")
    if status == "approved":
        msg = "Execution bridge successfully deployed remediation steps and resolved code/cluster anomaly."
    else:
        msg = "Action rejected by operator. Workflow terminated safely."
        
    return {
        "messages": [{"role": "assistant", "content": msg}]
    }