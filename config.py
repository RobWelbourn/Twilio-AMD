"""Configuration items"""

import os
import ngrok 

# Set these as environment variables.
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

# Phone number to use as caller id.  Should be a phone number in your Twilio account 
# or a verified caller id.  If left blank, use the caller id of the inbound call.
CALLER_ID = ""

# Phone number to call, if not using TaskRouter.  This should be replaced by user input, 
# e.g. through a web page.  (Lower case name indicates a variable, not a constant.)
dest_num = "+13395556789"

# Port for Flask to run on.  Defaults to 5000.
PORT = 5000

# External URL and hostname for the server, e.g. an Ngrok tunnel.  
# If not defined, defaults to localhost.
_urls = ngrok.get_public_urls()
SERVER_URL = _urls[0] if _urls else None
SERVER_NAME = SERVER_URL[SERVER_URL.find('://') + 3 : ] if SERVER_URL else None

# TaskRouter workspace name.  Used to extract key information about the workspace.
WORKSPACE_NAME = "AMD"

# Back-in-service timer for when an agent is temporarily unavailable.
TEMP_UNAVAILABLE_TIMER = 60
