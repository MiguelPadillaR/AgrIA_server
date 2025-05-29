import json
import os

def load_prompt_from_meta(meta_path: str, base_path: str = "AgrIA_server/assets/LLM_assets/prompts") -> dict:
    with open(meta_path, 'r', encoding='utf-8') as meta_file:
        meta = json.load(meta_file)
    
    prompt_file = os.path.join(base_path, meta['prompt_file'])
    with open(prompt_file, 'r', encoding='utf-8') as prompt_file:
        content = prompt_file.read()
    
    meta['content'] = content
    del meta['prompt_file']
    return meta