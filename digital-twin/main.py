import os
import shutil
import stat
import time
import gc
from git import Repo
from dotenv import load_dotenv
from typing import get_args
import tree_sitter_language_pack as tree
from src.risk_engine import calculate_predictive_risks
from src.ingestor import get_code_data, enrich_block, get_git_metadata
from src.services import generate_footprint
from src.db_client import supabase, save_memory_unit, save_edges

load_dotenv()

def run_ingestion_for_user(repo_url, user_id, project_id, status_callback):
    repo = None
    user_project_path = os.path.join("temp_projects", str(user_id), str(project_id))

    def remove_readonly(func, path, excinfo):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    try:
        # 1. IMMEDIATE START SIGNAL
        status_callback("STARTING", "Initializing environment...")

        # 2. SAFETY CHECK
        check = supabase.table("projects").select("id").eq("id", project_id).execute()
        if not check.data:
            status_callback("Error", None, "Project record missing from database.")
            return
        
        status_callback("PROCESSING", "Cleaning workspace...")
        
        # Windows Lock Fix
        if os.path.exists(user_project_path):
            gc.collect()
            time.sleep(0.5)
            shutil.rmtree(user_project_path, onerror=remove_readonly)

        # 3. CLONE
        status_callback("PROCESSING", "Cloning repository...")
        repo = Repo.clone_from(repo_url, user_project_path, depth=1)
        new_commit = repo.head.commit.hexsha

        # 4. SETUP LANGUAGES
        raw_args = get_args(tree.SupportedLanguage)
        languages = list(raw_args[0].__args__ if raw_args and hasattr(raw_args[0], '__args__') else raw_args)
         
        IGNORE_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.exe', '.dll', '.pyc', '.o', '.obj', 
                      '.css', '.svg', '.md', '.gitignore', '.csv', '.json', '.yaml', '.yml')
        SKIP_DIRS = {'.git', '.github', 'node_modules', 'venv', '__pycache__', 'dist', 'build'}

        # 5. SCAN
        status_callback("PROCESSING", "Scanning file structure...")
        current_scan_files = [] 
        all_valid_files = []
        
        for root, dirs, files in os.walk(user_project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.lower().endswith(IGNORE_EXT): continue
                all_valid_files.append(os.path.join(root, f))

        # 6. PROCESS UNITS
        for f_path in all_valid_files:
            rel_path = os.path.relpath(f_path, user_project_path)
            current_scan_files.append(rel_path)
            
            status_callback("PROCESSING", f"Analyzing logic in {rel_path}...")
            last_modified, author_email = get_git_metadata(user_project_path, f_path, repo)
            units = get_code_data(f_path, languages)
            
            if not units: continue

            for unit in units:
                node_id = f"{rel_path}::{unit['name']}"
                current_hash = generate_footprint(unit["code"])
                
                # Deduplication Check
                existing = supabase.table("memory_units").select("code_footprint").eq("project_id", project_id).eq("unit_name", node_id).execute()

                if not existing.data or existing.data[0]['code_footprint'] != current_hash:
                    intel = enrich_block(unit["code"], unit["name"])
                    if intel:
                        unit_payload = { 
                            "id": node_id, 
                            "file_path": rel_path, 
                            "unit_name": unit['name'],
                            "content": unit['code'],   
                            "last_modified_at": last_modified.isoformat() if last_modified else None,
                            "author_email": author_email,
                            **intel 
                        }
                        save_memory_unit(project_id, unit_payload)

                save_edges(project_id, node_id, unit["calls"])

        # 7. CLEANUP (Differential Sync)
        status_callback("PROCESSING", "Synchronizing graph state...")
        db_resp = supabase.table("memory_units").select("file_path").eq("project_id", project_id).execute()
        
        if db_resp.data:
            db_files = set([u['file_path'] for u in db_resp.data])
            scan_files = set(current_scan_files)
            deleted_files = db_files - scan_files
            for dead_file in deleted_files:
                supabase.table("memory_units").delete().eq("project_id", project_id).eq("file_path", dead_file).execute()

        # 8. FINALIZE RISKS
        supabase.table("projects").update({"last_commit": new_commit}).eq("id", project_id).execute()
        
        status_callback("PROCESSING", "Calculating predictive risks...")
        risk_count = calculate_predictive_risks(project_id)
        
        # 9. THE FINAL SIGNAL
        status_callback("DONE", f"Success! {risk_count} risks identified in commit {new_commit[:7]}.")

    except Exception as e:
        print(f"Ingestion Failed: {e}")
        status_callback("Error", None, str(e))
    finally:
        if repo:
            repo.close()
            del repo
        gc.collect()