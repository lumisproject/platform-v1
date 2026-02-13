import traceback
from src.services import get_embedding, get_llm_completion
from src.db_client import supabase, get_project_risks

def get_relevant_context(query, project_id):
    try:
        query_vector = get_embedding(query)
        params = {
            "query_embedding": query_vector,
            "match_threshold": 0.2,
            "match_count": 8,
            "filter_project_id": project_id
        }
        # Assuming your RPC returns columns: unit_name, content, summary, risk_score
        response = supabase.rpc("match_memory_units", params).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"!!! Error in get_relevant_context: {e}")
        return []

def get_graph_relationships(unit_name, project_id):
    """Traces dependencies using the unit_name string."""
    try:
        calls = supabase.table("graph_edges").select("target_unit_name")\
            .eq("project_id", project_id).eq("source_unit_name", unit_name).execute()
        
        called_by = supabase.table("graph_edges").select("source_unit_name")\
            .eq("project_id", project_id).eq("target_unit_name", unit_name).execute()
        
        targets = [item['target_unit_name'] for item in (calls.data or [])]
        sources = [item['source_unit_name'] for item in (called_by.data or [])]
        return targets, sources
    except Exception as e:
        print(f"!!! Error in get_graph_relationships: {e}")
        return [], []

def get_unit_source_code(unit_name, project_id):
    """Fetches raw code using unit_name (the unique text key)."""
    try:
        # Fixed: Querying by unit_name instead of id (which is a UUID)
        res = supabase.table("memory_units").select("content")\
            .eq("project_id", project_id).eq("unit_name", unit_name).maybe_single().execute()
        return res.data['content'] if (res.data and 'content' in res.data) else None
    except Exception:
        return None

def ask_twin_supabase(query, project_id):
    try:
        relevant_units = get_relevant_context(query, project_id)
        active_risks = get_project_risks(project_id) or []
        
        if not relevant_units and not active_risks:
            return "I couldn't find any relevant code context for this query."
        
        full_context = "### CODEBASE KNOWLEDGE GRAPH & SOURCE\n"
        
        for unit in relevant_units:
            # SCHEMA FIX: Mapping keys to your specific table columns
            name = unit.get('unit_name') or "unknown_unit" 
            summary = unit.get('summary') or "No summary available."
            code = unit.get('content') or "# Source code missing"
            risk_score = unit.get('risk_score', 0)
            file_path = unit.get('file_path', 'unknown_file')
            
            targets, sources = get_graph_relationships(name, project_id)
            
            full_context += f"--- UNIT: {name} (File: {file_path}) ---\n"
            if risk_score and risk_score > 60:
                full_context += f"[CRITICAL RISK SCORE: {risk_score}/100]\n"
            
            full_context += f"PURPOSE: {summary}\n"
            full_context += f"IMPLEMENTATION:\n{code[:1200]}\n"
            
            if sources:
                full_context += f"CALLERS: {', '.join(sources)}\n"
            if targets:
                full_context += f"DEPENDENCIES: {', '.join(targets)}\n"
                # Deep Vision for the primary dependency
                for t in targets[:1]:
                    dep_code = get_unit_source_code(t, project_id)
                    if dep_code:
                        full_context += f"  -> Implementation of {t}:\n{dep_code[:400]}...\n"
            full_context += "\n"

        if active_risks:
            full_context += "\n### SYSTEMIC ARCHITECTURAL RISKS\n"
            for r in active_risks:
                full_context += f"- [{r.get('severity', 'LOW').upper()}] {r.get('risk_type')}: {r.get('description')}\n"

        system_prompt = (
            "You are the Lumis Intelligence Digital Twin. You are a senior software architect with a cynical, investigative eye. "
            "Your goal is to move beyond simple code summaries and provide deep, non-obvious architectural insights.\n\n"
            "STRICT RESPONSE RULES:\n"
            "1. NO FLUFF: Skip greetings like 'Hello' or 'Based on the context'. Dive straight into the technical soul of the problem.\n"
            "2. CHAIN REACTION: If a user asks about a function, explain how changing it might break its inbound callers or its outbound dependencies.\n"
            "3. LOGICAL CRITIQUE: Point out technical debt, race conditions, or scaling issues you see in the provided source code.\n"
            "4. CONNECT DOTS: Use the graph relationships to infer system behavior even where code is missing.\n"
            "5. NO TEMPLATES: Never use phrases like 'It is important to note'. Be direct and high-density."
        )
        
        user_prompt = f"PROJECT CONTEXT:\n{full_context}\n\nUSER QUERY: {query}"
        
        return get_llm_completion(system_prompt, user_prompt)

    except Exception as e:
        print("--- CHAT EXECUTION FAILED ---")
        print(traceback.format_exc())
        return f"Internal Error: {str(e)}"