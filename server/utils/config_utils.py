# Read system instructions from a text file
def load_system_instructions(filepath):
    try:
        with open(filepath, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: System instruction file not found at {filepath}")
        return ""
