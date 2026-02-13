import os
from tree_sitter_language_pack import get_parser
from src.services import get_llm_completion, get_embedding, generate_footprint

def get_code_data(file_path, supported_langs):
    ext = os.path.splitext(file_path)[1].replace('.', '').lower()
    
    # Maps non-standard extensions to tree-sitter names
    extension_map = {
        "py": "python",
        "js": "javascript",
        "mjs": "javascript",
        "cjs": "javascript",
        "ts": "typescript",
        "rs": "rust",
        "rb": "ruby",
        "cs": "csharp",
        "sh": "bash",
        "yml": "yaml",
        "ps1": "powershell",
        "tf": "terraform",
        "md": "markdown"
    }
    
    lang_name = extension_map.get(ext, ext)
    
    # if not in list, skip it
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
            # Targets function-like structures across most languages
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