import os
import shutil
from git import Repo
from dotenv import load_dotenv
from typing import get_args
import tree_sitter_language_pack as tree
import stat
from src.ingestor import get_code_data, enrich_block
from src.services import generate_footprint
from src.db_client import supabase, save_memory_unit, save_edges

load_dotenv()

def run_ingestion_for_user(repo_url, user_id, project_id, status_callback):
    try:
        status_callback("Setup", f"Preparing environment...")
        base_path = "temp_projects"
        user_project_path = os.path.join(base_path, str(user_id), str(project_id))

        def remove_readonly(func, path, excinfo):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        # Remove the entire temp_projects directory before cloning to free space
        if os.path.exists(base_path):
            try:
                shutil.rmtree(base_path, onerror=remove_readonly)
            except Exception as e:
                status_callback("Error", None, f"Cleanup failed: {str(e)}")
                return
        # clone
        status_callback("Cloning", "Cloning repository...")
        repo = Repo.clone_from(repo_url, user_project_path, depth=1)
        new_commit = repo.head.commit.hexsha

        # supported languages
        raw_args = get_args(tree.SupportedLanguage)
        languages = list(raw_args[0].__args__ if raw_args and hasattr(raw_args[0], '__args__') else raw_args)
        
        IGNORE_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.exe', '.dll', '.pyc', '.o', '.obj')
        SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build'}

        # analyze
        status_callback("Analyzing", "Scanning file structure...")
        
        all_valid_files = []
        for root, dirs, files in os.walk(user_project_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.lower().endswith(IGNORE_EXT): continue
                all_valid_files.append(os.path.join(root, f))

        status_callback("Analyzing", f"Found {len(all_valid_files)} potential source files.")

        for f_path in all_valid_files:
            rel_path = os.path.relpath(f_path, user_project_path)
            status_callback("Processing", f"Reading {rel_path}...")
            
           # create code units
            units = get_code_data(f_path, languages)
            
            if not units: continue

            for unit in units:
                node_id = f"{rel_path}::{unit['name']}"
                current_hash = generate_footprint(unit["code"])
                
                # check if code logic is updated
                existing = supabase.table("memory_units").select("code_footprint").eq("project_id", project_id).eq("unit_name", node_id).execute()

                if not existing.data or existing.data[0]['code_footprint'] != current_hash:
                    status_callback("Updating", f"Logic change detected in {unit['name']}")
                    intel = enrich_block(unit["code"], unit["name"])
                    
                    if intel:
                        data = { "id": node_id, "file_path": rel_path, **intel }
                        save_memory_unit(project_id, data)
                        save_edges(project_id, node_id, unit["calls"])

        # finalize
        status_callback("Finalizing", "Updating project metadata...")
        supabase.table("projects").update({"last_commit": new_commit}).eq("id", project_id).execute()
        status_callback("DONE", "Ingestion complete.")

    except Exception as e:
        status_callback("Error", None, str(e))
        print(f"Ingestion Failed: {e}")