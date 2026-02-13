import os
import git
from datetime import datetime
from tree_sitter_language_pack import get_parser
from src.services import get_llm_completion, get_embedding, generate_footprint
from src.db_client import supabase

# --- Git Metadata Extraction ---
def get_git_metadata(repo_path, file_path, repo_obj=None):
    try:
        repo = repo_obj if repo_obj else git.Repo(repo_path)
        rel_path = os.path.relpath(file_path, repo_path)
        commits = list(repo.iter_commits(paths=rel_path, max_count=1))
        
        if not commits:
            return None, None
            
        commit = commits[0]
        return commit.committed_datetime, commit.author.email
    except Exception as e:
        print(f"Warning: Could not fetch git metadata for {file_path}: {e}")
        return None, None

def get_code_data(file_path, supported_langs):
    ext = os.path.splitext(file_path)[1].replace('.', '').lower()
    extension_map = {
        "py": "python", "js": "javascript", "mjs": "javascript",
        "cjs": "javascript", "ts": "typescript", "rs": "rust",
        "rb": "ruby", "cs": "csharp", "sh": "bash",
        "yml": "yaml", "ps1": "powershell", "tf": "terraform", "md": "markdown"
    }
    
    lang_name = extension_map.get(ext, ext)
    if lang_name not in supported_langs:
        return []
    
    try:
        parser = get_parser(lang_name)
        if not parser: return []

        with open(file_path, "rb") as f:
            content = f.read()
            tree = parser.parse(content)
        
        results = []
        def walk(node):
            if node.type in ["function_definition", "method_definition", "function_declaration", "method_declaration"]:
                name_node = node.child_by_field_name('name')
                func_name = content[name_node.start_byte:name_node.end_byte].decode('utf-8', errors='ignore') if name_node else "anonymous"
                func_body = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                
                calls = []
                def find_calls(n):
                    if n.type in ["call", "call_expression"]:
                        calls.append(content[n.start_byte:n.end_byte].decode('utf-8', errors='ignore'))
                    for child in n.children: find_calls(child)
                
                find_calls(node)
                results.append({"name": func_name, "code": func_body, "calls": list(set(calls))})

            for child in node.children: walk(child)

        walk(tree.root_node)
        return results
    except Exception as e:
        print(f"Parsing error in {file_path}: {e}")
        return []

def enrich_block(code_block, unit_name):
    system_msg = """You are a technical code analyst. Summarize the core logic in one clear sentence.
    If purely boilerplate/empty, return: SKIP"""
    
    summary = get_llm_completion(system_msg, f"Function Name: {unit_name}\nCode:\n{code_block}")
    
    if not summary or "SKIP" in summary.upper():
        return None
    
    return {
        "summary": summary,
        "embedding": get_embedding(code_block),
        "footprint": generate_footprint(code_block)
    }

# --- NEW: Orchestration with Cleanup Logic ---
def ingest_repo(repo_url, project_id, user_id, progress_callback=None):
    repo_path = f"./temp_repos/{project_id}"
    
    if progress_callback: progress_callback("CLONING", f"Cloning {repo_url}...")
    
    if os.path.exists(repo_path):
        repo = git.Repo(repo_path)
        repo.remotes.origin.pull()
    else:
        repo = git.Repo.clone_from(repo_url, repo_path)

    # Track files found in THIS scan for differential sync
    current_scan_files = []
    supported_langs = ["python", "javascript", "typescript"]

    # 1. Process and Save Units
    for root, _, files in os.walk(repo_path):
        if '.git' in root: continue
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path)
            
            # Identify if it's a code file
            blocks = get_code_data(file_path, supported_langs)
            if not blocks: continue
            
            current_scan_files.append(rel_path)
            last_mod, author = get_git_metadata(repo_path, file_path, repo)

            for block in blocks:
                if progress_callback: progress_callback("PROCESSING", f"Analyzing {rel_path} -> {block['name']}")
                
                analysis = enrich_block(block['code'], block['name'])
                if not analysis: continue

                # Upsert into Supabase (Includes 'content' for Risk Engine)
                supabase.table("memory_units").upsert({
                    "project_id": project_id,
                    "unit_name": block['name'],
                    "file_path": rel_path,
                    "content": block['code'],  # Added for Deep Analysis
                    "summary": analysis['summary'],
                    "embedding": analysis['embedding'],
                    "footprint": analysis['footprint'],
                    "last_modified_at": last_mod.isoformat() if last_mod else None,
                    "author_email": author
                }).execute()

    # 2. Cleanup: Remove deleted files from DB
    if progress_callback: progress_callback("CLEANUP", "Removing orphan code blocks...")
    
    db_units = supabase.table("memory_units")\
        .select("file_path")\
        .eq("project_id", project_id)\
        .execute()
    
    if db_units.data:
        db_files = set([u['file_path'] for u in db_units.data])
        scan_files = set(current_scan_files)
        deleted_files = db_files - scan_files

        for dead_file in deleted_files:
            supabase.table("memory_units")\
                .delete()\
                .eq("project_id", project_id)\
                .eq("file_path", dead_file)\
                .execute()

    if progress_callback: progress_callback("DONE", "Ingestion and Cleanup complete.")