import json
import os

def load_prompt_from_json(json_path: str, base_path: str = "./assets/LLM_assets/prompts", get_short_description: bool = True) -> dict:
    full_json_path = os.path.join(base_path, json_path).replace("\\", "/")

    # Read JSON and get short/long description
    with open(full_json_path, 'r', encoding='utf-8') as json_file:
        meta = json.load(json_file)
    desc_type = meta.get('short') if get_short_description else meta.get('long')
    desc_filename = desc_type["prompt_filepath"]

    # Read desc file and get content
    prompt_file = os.path.join(base_path, desc_filename).replace("\\", "/")
    with open(prompt_file, 'r', encoding='utf-8') as prompt_file:
        content = prompt_file.read()
        
    meta['content'] = content
    del desc_filename
    return content