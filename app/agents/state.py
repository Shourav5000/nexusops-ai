# app/agents/state.py
from typing import Annotated, List, TypedDict
import operator


class AgentState(TypedDict):
    messages: Annotated[List[dict], operator.add]
    current_task: str
    retrieved_docs: List[str]
    diagnostics_report: str
    requires_approval: bool
    approval_status: str
    final_output: str