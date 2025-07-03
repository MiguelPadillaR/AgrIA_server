# AgrIA_server

This is the server side of the Agricultural Imaging Assistant (AgrIA). It includes information on how to setup and run the server side of AgrIA.

## Requirements:
You will need to create a virtual environment with`conda` since it simplifies the package handling of some libraries, so having `conda` already installed is a must.

You will need access to KHAOS' [`sigpac-tools`](https://github.com/KhaosResearch/sigpac-tools.git@07145bcaebcdf37bc5b24191950a3f0a666841b4) repository in order to be able to fully run AgrIA's server. **To access the repository, contact [KHAOS Research](https://khaos.uma.es/?page_id=101) group.**

## Installation & Setup

### Python enviroment creation and activation:
Run the following commnands to create and activate the `agria_server_env` environment.
```bash
conda env create -f environment.yml
conda activate agria_server_env
```

### System environment setup:
You will need to rename the `.env_example` file to `env` and fill it with your own data.

**Content of your `.env` file:**
```bash
# Replace variables with your data and rename file to ".env"
GEMINI_API_KEY=YOUR_API_KEY
UI_URL=YOUR_FRONTEND_URL
API_PORT=XXXX
API_URL=http://yourApiDomain.com

# Contact authors to gain access to these database credentials and files
MINIO_ENDPOINT=255.000.000.000:0000
MINIO_ACCESS_KEY=minio-access-key
MINIO_SECRET_KEY="minio-secret-key"
bucket_name="bucket-name"

GEOMETRY_FILE = geometry-file.kml
```
**To get credentials to access the MinIO image database, contact [KHAOS Research](https://khaos.uma.es/?page_id=101) group.**

## Server initialization:
After activating and setting up all environments, run the server by simply using:

```bash
python run.py
```

## Project structure:
By the end of the setup process, your directory structure should look like this:

```raw
Agria_server:.
|   .env
|   .gitignore
|   environment.yml
|   README.md
|   run.py
|   
+---assets
|   |       
|   \---geojson_assets
|   |       *.kml
|   |       
|   \---LLM_assets
|       +---context
|       |   |   context_document_links.json
|       |   |   
|       |   \---files
|       |           220930_nota_aclaratoria_aplicacion_eco_regimenes.pdf
|       |           230306_pmf4-ecorregimenes_v4.pdf
|       |           
|       \---prompts
|               LLM-full_desc_example.txt
|               LLM-full_desc_prompt.txt
|               LLM-role_prompt.txt
|               LLM-tldr_desc_example.txt
|               LLM-tldr_desc_prompt.txt
|               prompt_list.json
|               
+---server
|   |   __init__.py
|   |   
|   +---config
|   |       chat_config.py
|   |       config.py
|   |       constants.py
|   |       env_config.py
|   |       llm_client.py
|   |           
|   +---endpoints
|   |       chat.py
|   |       parcel_finder.py
|   |           
|   +---services
|   |       chat_service.py
|   |       llm_services.py
|   |           
|   +---utils
|           chat_utils.py
|           config_utils.py
|           llm_utils.py
|           parcel_finder_utils.py
|           
\---test
        conftest.py
        test_hello.py
        test_image_upload.py
        test_user_input.py
```

### Components overview:
This is a brief overview of each main directory in the project structure:
- `assets`: All resources the server uses are stored here.
  - `geojson_assets`: Ideally, where you'd put your `GEOMETRY_FILE`, but as long as you assign the variable the correct path to the `.kml` file, it doesn't matter.
  - `llm_assets`: Stores context files and prompts for LLM initialization and role assignment. JSON files contain file paths information and are accessed by the server to pass to AgrIA as system instructions.
- `server`: Contains all server's main logic components and directories:
  - `config`: Holds configuration-related files: from constants used all-over to initialization configuration.
  - `endpoints`: Keeps all endpoints access and methods to a single file for each UI component.
  - `services`: Maintains files with all the methods that call external services outside of our project scope.
  - `utils`: An assortment of functions and methods that  help  all the data processing that mainly comes from endpoint input requests.
- `tests`: A baterry of integration tests for the server **(TODO)**.