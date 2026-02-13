from datetime import datetime, timezone, timedelta
from src import db_client
from src.services import get_llm_completion
import json

LEGACY_THRESHOLD_DAYS = 90

def assess_risks(project_id, changed_unit_ids):
    """
    Analyzes the impact of changes and detects legacy conflicts.
    changed_unit_ids: List of unit_names (str) that were modified.
    """
    print(f"Starting Impact Analysis for {len(changed_unit_ids)} units...")
    
    risks = []
    
    for unit_name in changed_unit_ids:
        # 1. Find Callers (Impact Radius)
        callers = db_client.get_callers_of(project_id, unit_name)
        
        if not callers:
            continue
            
        print(f"Unit {unit_name} impacts {len(callers)} other units.")
        
        for caller_name in callers:
            caller_node = db_client.get_memory_unit(project_id, caller_name)
            if not caller_node: continue
            
            # 2. Check for Legacy
            last_updated_str = caller_node.get("last_updated")
            is_legacy = False
            
            if last_updated_str:
                try:
                    last_updated = datetime.fromisoformat(last_updated_str)
                    if datetime.now(timezone.utc) - last_updated > timedelta(days=LEGACY_THRESHOLD_DAYS):
                        is_legacy = True
                except ValueError:
                    pass # Date format error, skip legacy check
            
            # 3. LLM Signature Mismatch Check
            # We need the code of the CHANGED unit and the CALLER unit to see if they conflict.
            # Fetch changed unit content
            changed_node = db_client.get_memory_unit(project_id, unit_name)
            if not changed_node: continue

            check = check_architectural_conflict(changed_node, caller_node, is_legacy)
            
            if check:
                risks.append({
                    "source": unit_name,
                    "target": caller_name,
                    "risk_type": "Architectural Conflict" if not is_legacy else "Legacy Conflict",
                    "details": check
                })

    # Report Risks
    if risks:
        print("\n\n====== PREDICTIVE RISK ALERT ======")
        for r in risks:
            print(f"[{r['risk_type']}] {r['source']} -> {r['target']}")
            print(f"Details: {r['details']}")
            
            # Persist
            db_client.save_risk(project_id, r)
            
        print("===================================\n")
    else:
        print("Impact Analysis: No significant risks detected.")

def check_architectural_conflict(changed_node, caller_node, is_legacy):
    prompt = f"""
    Analyze if the change in 'Source' breaks the 'Target' unit.
    
    Source Function (Recently Changed):
    {changed_node.get('summary')}
    
    Target Function (Caller):
    {caller_node.get('summary')}
    
    Context:
    Target unit is {'LEGACY (not updated in 90+ days)' if is_legacy else 'Active'}.
    
    Task:
    Return a short warning string ONLY if there is a high risk of breakage (signature mismatch, assumption violation).
    If low risk, return empty string.
    """
    
    response = get_llm_completion("You are a Senior Architect.", prompt)
    return response if response and len(response) > 5 else None
