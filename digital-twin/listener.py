from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.db_client import supabase
from main import run_ingestion_for_user
from chat import ask_twin_supabase

app = FastAPI(title="Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global store for ingestion status
ingestion_status = {}

# Pydantic models for automatic validation
class IngestRequest(BaseModel):
    user_id: str
    repo_url: str

class ChatRequest(BaseModel):
    query: str
    project_id: str

def update_progress(project_id: str, step: str, log_message: str = None, error: str = None):
    if project_id not in ingestion_status:
        ingestion_status[project_id] = {"status": "init", "logs": []}
    
    state = ingestion_status[project_id]
    state["step"] = step
    if log_message:
        state["logs"].append(log_message)
    
    if error:
        state["status"] = "failed"
        state["error"] = str(error)
    elif step == "DONE":
        state["status"] = "completed"
    else:
        state["status"] = "processing"

@app.post("/api/ingest")
async def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    try:
        # Create Project in DB
        project = supabase.table("projects").insert({
            "user_id": req.user_id, 
            "repo_url": req.repo_url,
            "last_commit": "pending"
        }).execute()
        
        if not project.data:
            raise Exception("Failed to create project in database.")

        project_id = project.data[0]['id']
        
        # Initialize Status
        ingestion_status[project_id] = {
            "status": "starting", 
            "step": "Initializing...", 
            "logs": ["Request received."],
            "error": None
        }
        
        # FastAPI's BackgroundTasks handles the thread management for you
        background_tasks.add_task(
            run_ingestion_for_user, 
            req.repo_url, 
            req.user_id, 
            project_id, 
            lambda s, l=None, e=None: update_progress(project_id, s, l, e)
        )
        
        return {"project_id": project_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ingest/status/{project_id}")
async def get_status(project_id: str):
    status = ingestion_status.get(project_id)
    if not status:
        raise HTTPException(status_code=404, detail="Project not found")
    return status

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        response = ask_twin_supabase(req.query, req.project_id)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/webhook/{user_id}/{project_id}")
async def github_webhook(user_id: str, project_id: str, request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    
    # verify the a push event
    if "ref" not in payload or "after" not in payload:
        return {"status": "ignored", "reason": "Not a push event"}

    new_commit_sha = payload["after"]
    repo_url = payload["repository"]["clone_url"]

    project = supabase.table("projects").select("last_commit").eq("id", project_id).eq("user_id", user_id).single().execute()

    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # avoid redundant processing if already at this commit
    if project.data["last_commit"] == new_commit_sha:
        return {"status": "already_synced"}

    # trigger background incremental sync
    background_tasks.add_task(
        run_ingestion_for_user,
        repo_url,
        user_id,
        project_id,
        lambda step, log=None, err=None: print(f"[{project_id}] {step}: {log or err}")
    )

    return {"status": "sync_triggered", "commit": new_commit_sha}

@app.get("/")
def main_page():
    return {
        "status": "online",
        "service": "Lumis Intelligence Orchestrator",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000) # '0.0.0.0' & 5000 must be changed later in deployment 