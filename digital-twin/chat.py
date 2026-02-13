from src.services import get_embedding, get_llm_completion
from src.db_client import supabase

def get_relevant_context(query, project_id):
    query_vector = get_embedding(query)
    
    params = {
        "query_embedding": query_vector,
        "match_threshold": 0.2,
        "match_count": 10,
        "filter_project_id": project_id
    }
    
    response = supabase.rpc("match_memory_units", params).execute()
    return response.data

def get_graph_relationships(unit_name, project_id):
    # what this unit calls
    calls = supabase.table("graph_edges")\
        .select("target_unit_name")\
        .eq("project_id", project_id)\
        .eq("source_unit_name", unit_name)\
        .execute()
        
    # what calls this unit
    called_by = supabase.table("graph_edges")\
        .select("source_unit_name")\
        .eq("project_id", project_id)\
        .eq("target_unit_name", unit_name)\
        .execute()
        
    targets = [item['target_unit_name'] for item in calls.data]
    sources = [item['source_unit_name'] for item in called_by.data]
    
    return targets, sources

def ask_twin_supabase(query, project_id):
    relevant_units = get_relevant_context(query, project_id)
    
    if not relevant_units:
        return "I couldn't find any relevant code in this project to answer your question."
    
    # build full context with units and relationships
    full_context = ""
    for unit in relevant_units:
        name = unit['unit_name']
        summary = unit['summary']
        
        targets, sources = get_graph_relationships(name, project_id)
        
        full_context += f"Function: {name}\nSummary: {summary}\n"
        if sources:
            full_context += f"  - Called by: {', '.join(sources)}\n"
        if targets:
            full_context += f"  - Calls: {', '.join(targets)}\n"
        full_context += "\n"

    system_prompt = (
        "You are Lumis, the AI Digital Twin for this software project. "
        "Your goal is to explain complex code in a clear, architectural, and visually appealing way. "
        
        "STRICT FORMATTING RULES:\n"
        "1. Use Markdown headers (###) for sections.\n"
        "2. Use **bolding** for function names and variables.\n"
        "3. Use Mermaid-style flowcharts or structured lists for logic flow.\n"
        "4. Use Code Blocks (```python) for any code snippets.\n"
        "5. Use 'Callouts' like '> [!INFO]' or '💡 Tip' to highlight important architectural notes.\n"
        "6. Keep explanations concise but technically accurate.\n"
        
        "Structure your response as follows:\n"
        "- **Overview**: A 1-sentence summary.\n"
        "- **Logic Flow**: A numbered list of steps.\n"
        "- **Component Relationships**: How this block interacts with others (using the provided graph data).\n"
        "- **Input/Output**: Clear definition of parameters and returns."
    )
    
    user_prompt = f"Context from codebase:\n{full_context}\n\nQuestion: {query}"
    
    return get_llm_completion(system_prompt, user_prompt)