from datetime import datetime, timezone
from src.db_client import get_project_data, save_risk_alerts, update_unit_risk_scores
from src.services import get_llm_completion

def analyze_conflict_with_llm(source_name, source_code, target_name, target_code):
    """
    Uses the LLM to determine if the interaction between new and legacy code is dangerous.
    """
    system_prompt = (
        "You are a Senior Software Architect specializing in legacy modernization. "
        "Analyze the interaction between a RECENTLY MODIFIED function and a LEGACY function (unchanged for months). "
        "Predict if the recent changes might break assumptions in the legacy code. "
        "Be concise. Focus on data types, null handling, and logic assumptions."
    )
    
    user_prompt = (
        f"--- RECENT CODE ({source_name}) ---\n"
        f"{source_code}\n\n"
        f"--- LEGACY CODE ({target_name}) ---\n"
        f"{target_code}\n\n"
        "TASK: Explain the potential risk in 1-2 sentences. If the risk is generic, say 'Standard dependency risk'. "
        "If you see a specific mismatch (e.g. arguments, types), explain it."
    )
    
    analysis = get_llm_completion(system_prompt, user_prompt)
    return analysis if analysis else "Standard dependency risk detected."

def calculate_predictive_risks(project_id):
    print(f"Starting Risk Analysis for {project_id}...")
    
    # 1. Fetch Graph Data
    units, edges = get_project_data(project_id)
    if not units:
        return 0

    # 2. Define Thresholds
    now = datetime.now(timezone.utc)
    LEGACY_THRESHOLD_DAYS = 180  # 6 months
    RECENT_THRESHOLD_DAYS = 30   # 1 month
    
    legacy_units = {}  # Map: unit_name -> unit_data
    recent_units = set()
    unit_map = {u['unit_name']: u for u in units}
    
    # 3. Classify Nodes (Legacy vs Recent)
    for unit in units:
        if not unit.get('last_modified_at'):
            continue
            
        # Parse ISO date string from Supabase
        try:
            last_mod = datetime.fromisoformat(unit['last_modified_at'].replace('Z', '+00:00'))
        except ValueError:
            continue 
            
        age_days = (now - last_mod).days
        
        if age_days > LEGACY_THRESHOLD_DAYS:
            legacy_units[unit['unit_name']] = unit
        elif age_days < RECENT_THRESHOLD_DAYS:
            recent_units.add(unit['unit_name'])

    # 4. Detect Conflicts (Edges)
    risks = []
    risk_scores = {} # unit_name -> int
    
    # Analyze dependencies
    print(f"Analyzing {len(edges)} dependencies for conflicts...")
    
    for edge in edges:
        source = edge['source_unit_name']
        target = edge['target_unit_name']
        
        # RISK PATTERN: Recent Code calling Legacy Code
        if source in recent_units and target in legacy_units:
            target_unit = legacy_units[target]
            source_unit = unit_map[source]
            
            print(f"Detected conflict: {source} -> {target}")
            
            # --- NEW: LLM Semantic Analysis ---
            # We fetch the code content and ask the LLM for a specific reason
            analysis = analyze_conflict_with_llm(
                source, source_unit.get('content', ''),
                target, target_unit.get('content', '')
            )
            
            description = (
                f"Legacy Conflict: Active code '{source}' depends on '{target}' "
                f"(last touched {target_unit.get('last_modified_at', 'unknown')}).\n"
                f"AI Analysis: {analysis}"
            )
            # ----------------------------------
            
            risks.append({
                "project_id": project_id,
                "risk_type": "Legacy Conflict",
                "severity": "Medium", 
                "description": description,
                "affected_units": [source, target]
            })
            
            # Increase Risk Scores
            risk_scores[source] = risk_scores.get(source, 0) + 25
            risk_scores[target] = risk_scores.get(target, 0) + 10

    # 5. Base Risk Scores (Age Factors)
    score_updates = []
    for unit in units:
        u_name = unit['unit_name']
        current_score = risk_scores.get(u_name, 0)
        
        # If it's legacy, it has a baseline risk
        if u_name in legacy_units:
            current_score += 10
            
        # Cap at 100
        final_score = min(current_score, 100)
        
        if final_score > 0:
            score_updates.append({
                "project_id": project_id,
                "unit_name": u_name,
                "risk_score": final_score
            })

    # 6. Save Results
    print(f"Saving {len(risks)} legacy conflicts.")
    save_risk_alerts(project_id, risks)
    update_unit_risk_scores(score_updates)
    
    return len(risks)