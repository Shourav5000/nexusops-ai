from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import AgentState
from app.agents.nodes import router_node, rag_agent_node, diagnostics_agent_node, apply_fix_node


def build_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("diagnostics_agent", diagnostics_agent_node)
    workflow.add_node("apply_fix", apply_fix_node)

    workflow.set_entry_point("router")

    workflow.add_conditional_edges(
        "router",
        lambda state: state["current_task"],
        {
            "rag_agent": "rag_agent",
            "diagnostics_agent": "diagnostics_agent",
        },
    )

    workflow.add_edge("rag_agent", END)
    workflow.add_edge("diagnostics_agent", "apply_fix")
    workflow.add_edge("apply_fix", END)

    memory = MemorySaver()
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["apply_fix"],
    )
