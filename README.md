# NexusOps AI 🚀

An enterprise-grade, production-ready multi-agent operations copilot designed to automate infrastructure troubleshooting, runbook retrieval, and incident remediation with strict Human-in-the-Loop (HITL) governance.

## Architecture & Tech Stack

* **Infrastructure & Cloud Services:** AWS EC2 (Elastic Compute Cloud) for hosting and compute, AWS VPC / Networking security groups, and AWS IAM (Identity and Access Management) for role-based permissions and secure credential provisioning.
* **Containerization & Orchestration:** Docker, Docker Compose, LangGraph (state management, checkpointing with `AsyncPostgresSaver`, and interrupt-driven execution).
* **AI Engine:** Anthropic Claude Sonnet 5 (`claude-sonnet-5`) powering advanced multi-agent reasoning, intent routing, and incident synthesis.
* **Retrieval-Augmented Generation (RAG):** FAISS vector store combined with custom technical runbooks for low-latency context matching.
* **Backend API & Database:** FastAPI with asynchronous request handling, PostgreSQL session persistence, and persistent thread-session management.
* **Frontend:** Custom enterprise console featuring real-time governance cards, session context management, audio dictation via Web Speech API, multimodal vision parsing, and interactive workflow triggers.

## Core Features

1. **Intelligent Intent Routing:** Dynamically parses incoming operational anomalies to dispatch either the Documentation RAG Agent or the Deep Diagnostics Agent.
2. **Context-Aware Runbook Synthesis:** Queries local FAISS vector indices to ground AI responses in verified internal engineering runbooks.
3. **Human-in-the-Loop (HITL) Governance:** Halts execution automatically before making destructive or high-impact operational changes, requiring explicit operator authorization.
4. **Stateful Audit Trails:** Uses LangGraph checkpointing and PostgreSQL to maintain persistent, resumable multi-turn diagnostic sessions across threads.

## Local Development & Deployment

To build and run the containerized application locally using Docker Compose:

```bash
docker compose up --build -d

nexusops-ai/
├── app/
│   ├── agents/          # LangGraph workflow graphs, state definitions, and agent nodes
│   ├── services/        # FAISS vector store and retrieval logic
│   ├── static/          # Enterprise UI (HTML, CSS, JS)
│   └── main.py          # FastAPI application entrypoint and resume endpoints
├── data/                # Technical runbooks and vector embeddings
├── docker-compose.yml   # Container orchestration configuration
├── Dockerfile           # App container specification
├── .env                 # Environment secrets (Anthropic API keys, PostgreSQL URI)
└── requirements.txt     # Python dependency specifications (fastapi, langgraph, psycopg, etc.)