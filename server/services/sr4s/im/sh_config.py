from sentinelhub import SHConfig
from dotenv import load_dotenv

import os
import logging

# Setup logging
# logging.basicConfig(level=logging.DEBUG)
# logging.captureWarnings(True)

load_dotenv()

# Setup Copernicus client credentials
CLIENT_ID = os.getenv('COPERNICUS_CLIENT_ID')
CLIENT_SECRET = os.getenv('COPERNICUS_CLIENT_SECRET')
CONFIG_NAME = str(os.getenv('COPERNICUS_CONFIG_NAME'))

# Setup config params for Copernicus dataspace Ecosystem users
config = SHConfig()

config.sh_client_id = CLIENT_ID
config.sh_client_secret = CLIENT_SECRET
config.sh_base_url = 'https://sh.dataspace.copernicus.eu'
config.sh_token_url = 'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token'

config.save(CONFIG_NAME)