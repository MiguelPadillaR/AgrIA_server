# AgrIA_server
This is the server side of the Agricultural Imaging Assistant (AgrIA)

*Add more desc...*

## Installation & Setup
You will need to create a virtual environment (preferably with`conda`) before launching the server.

You will need access to KHAOS' [`sigpac-tools`](https://github.com/KhaosResearch/sigpac-tools.git@07145bcaebcdf37bc5b24191950a3f0a666841b4) repository in order to be able to fully run AgrIA's server.

Run the following commnands to create and activate the `agria_server_env` environment.
```code:bash
conda env create -f environment.yml
conda activate agria_server_env
```
## Server initialization:
After activating the environment, run the server by simply using:

```code:bash
python run.py
```