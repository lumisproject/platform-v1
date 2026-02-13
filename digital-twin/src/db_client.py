import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase: Client = create_client(url, key)

def get_project_risks(project_id):
    """Fetches active risk alerts for the project."""
    # We prioritize High/Critical risks and recent ones
    response = supabase.table("project_risks").select("*").eq("project_id", project_id).order("created_at", desc=True).limit(10).execute()
    return response.data

def get_project_data(project_id):
    units_resp = supabase.table("memory_units").select("unit_name, file_path, last_modified_at, author_email, content").eq("project_id", project_id).execute()
    edges_resp = supabase.table("graph_edges").select("source_unit_name, target_unit_name").eq("project_id", project_id).execute()
    return units_resp.data, edges_resp.data

def save_risk_alerts(project_id, risks):
    if not risks:
        return
    
    supabase.table("project_risks").delete().eq("project_id", project_id).eq("risk_type", "Legacy Conflict").execute()
    supabase.table("project_risks").insert(risks).execute()

def update_unit_risk_scores(updates):
    if not updates:
        return
    try:
        for update in updates:
            supabase.table("memory_units") \
                .update({"risk_score": update["risk_score"]}) \
                .eq("project_id", update["project_id"]) \
                .eq("unit_name", update["unit_name"]) \
                .execute()
    except Exception as e:
        print(f"Failed to update risk scores: {e}")

def save_memory_unit(project_id, unit_data):
    payload = {
        "project_id": project_id,
        "unit_name": unit_data["id"],
        "file_path": unit_data["file_path"],
        "content": unit_data.get("content"),
        "summary": unit_data["summary"],
        "code_footprint": unit_data["footprint"],
        "embedding": unit_data["embedding"],
        "last_modified_at": unit_data.get("last_modified_at"),
        "author_email": unit_data.get("author_email")
    }
    return supabase.table("memory_units").upsert(
        payload, 
        on_conflict="project_id, unit_name"
    ).execute()

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
    
    # Using upsert for edges as well
    return supabase.table("graph_edges").upsert(
        edges, 
        on_conflict="project_id, source_unit_name, target_unit_name"
    ).execute()

def save_edges(project_id, source_unit_name, calls_list):
    if not calls_list:
        return
    # This prevents duplication and stale connections
    supabase.table("graph_edges")\
        .delete()\
        .eq("project_id", project_id)\
        .eq("source_unit_name", source_unit_name)\
        .execute()
        
    edges = []
    for target in calls_list:
        edges.append({
            "project_id": project_id, 
            "source_unit_name": source_unit_name, 
            "target_unit_name": target
        })
    
    # 2. INSERT NEW EDGES
    if edges:
        supabase.table("graph_edges").insert(edges).execute()