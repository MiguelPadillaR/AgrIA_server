# AgrIA_server
This is the server side of the Agricultural Imaging Assistant (AgrIA)

<Add more desc>

## Installation & Setup
You will need to create a virtual environment (`pip` for MacOS or `conda` for Windows) before launching the server.
### Linux/MacOS
- Using a terminal
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
### Windows
- You will need `conda` installed. You can follow a guide [here](https://docs.conda.io/projects/conda/en/latest/user-guide/install/windows.html). After successfully installing `conda`, create and setup the environment with the following:
```bash
conda init
conda env create -f environment.yml
conda activate agria_server_env
```
- This will generate and activate a `conda` virtual environment called `agria_server_env`.