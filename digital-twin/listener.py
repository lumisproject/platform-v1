from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.db_client import supabase, get_project_risks  # <--- UPDATED IMPORT
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
        ingestion_status[project_id] = {"status": "IDLE", "logs": []}
    
    state = ingestion_status[project_id]
    state["step"] = step
    if log_message:
        state["logs"].append(log_message)
    
    if error:
        state["status"] = "Error"
        state["error"] = str(error)
    elif step == "DONE":
        state["status"] = "DONE"
    elif step == "STARTING":
        state["status"] = "STARTING"
    else:
        state["status"] = "PROCESSING"

@app.get("/api/ingest/status/{project_id}")
async def get_status(project_id: str):
    status = ingestion_status.get(project_id)
    if not status:
        return {"status": "IDLE"}
    
    current_status_val = status.get("status")
    
    # If the status is DONE, we grab the data to return it, 
    # then IMMEDIATELY reset it to IDLE for the next call.
    if current_status_val == "DONE":
        response = status.copy()
        ingestion_status[project_id] = {"status": "IDLE", "logs": []}
        print(f"Status for {project_id} reset to IDLE after DONE check.")
        return response
        
    return status

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

@app.get("/api/risks/{project_id}")
async def get_risks(project_id: str):
    try:
        risks = get_project_risks(project_id)
        return {"status": "success", "risks": risks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        response = ask_twin_supabase(req.query, req.project_id)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/webhook/{user_id}/{project_id}")
async def github_webhook(user_id: str, project_id: str, request: Request, background_tasks: BackgroundTasks):
    try:
        # 1. Fetch project safely using Python-style snake_case
        # Use maybe_single() to avoid crashing if the ID is wrong
        res = supabase.table("projects") \
            .select("*") \
            .eq("id", project_id) \
            .eq("user_id", user_id) \
            .maybe_single() \
            .execute()

        # Handle missing project (common if DB was truncated)
        if not res or not res.data:
            print(f"Webhook Ignored: Project {project_id} not found for user {user_id}")
            return {"status": "ignored", "reason": "project_not_found"}

        payload = await request.json()

        # 2. Handle GitHub's "Zen" test ping (sent when webhook is first created)
        if "zen" in payload:
            print("GitHub Zen ping received. Connection verified.")
            return {"status": "ok", "message": "Lumis is listening"}

        # 3. Handle Push Events
        ref = payload.get("ref", "")
        # Only trigger for pushes to branches (ignore tags/deletions)
        if "refs/heads/" in ref:
            new_sha = payload.get("after")
            repo_url = payload.get("repository", {}).get("clone_url")
            
            print(f"Webhook Trigger: Push detected on {ref} (Commit: {new_sha[:7]})")

            # Update status immediately so the Dashboard polls and opens the Wizard
            update_progress(
                project_id, 
                "STARTING", 
                f"GitHub Push detected ({new_sha[:7]}). Initializing Twin Sync..."
            )

            # 4. Fire and forget: Run the full ingestion in the background
            background_tasks.add_task(
                run_ingestion_for_user,
                repo_url,
                user_id,
                project_id,
                lambda s, l=None, e=None: update_progress(project_id, s, l, e)
            )

            return {"status": "sync_started", "commit": new_sha}

        return {"status": "ignored", "reason": "not_a_push_event"}

    except Exception as e:
        print(f"CRITICAL: Webhook Processing Error: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/")
def main_page():
    return {
        "status": "online",
        "service": "Lumis Intelligence Orchestrator",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)