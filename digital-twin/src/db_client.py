import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(url, key)

def save_memory_unit(project_id, unit_data):
    payload = {
        "project_id": project_id,
        "unit_name": unit_data["id"],
        "file_path": unit_data["file_path"],
        "summary": unit_data["summary"],
        "code_footprint": unit_data["footprint"],
        "embedding": unit_data["embedding"]
    }
    return supabase.table("memory_units").upsert(payload, on_conflict="project_id, unit_name").execute()

def save_edges(project_id, source_unit_name, calls_list):
    if not calls_list:
        return
        
    edges = []
    for target in calls_list:
        edges.append({
            "project_id": project_id, 
            "source_unit_name": source_unit_name, 
            "target_unit_name": target
        })
    
    # Delete old edges for this source to avoid stale connections, then insert new ones
    supabase.table("graph_edges").delete().eq("project_id", project_id).eq("source_unit_name", source_unit_name).execute()
    supabase.table("graph_edges").insert(edges).execute()