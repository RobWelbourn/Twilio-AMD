"""Configuration items"""

import os
import ngrok 

# Set these as environment variables.
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')

# Phone number to use as caller id.  Should be a phone number in your Twilio
# account or a verified caller id.  Accounts which have "Any Caller Id" permission
# may instead choose to use the caller id of the inbound call.
caller_id = "+16175551234"

# Phone number to call.  This should be replaced by user input, e.g. through
# a web page.
dest_num = "+13395556789"

# Port for Flask to run on.  Defaults to 5000.
PORT = 5000

# Exernal URL and hostname for the server, e.g. an Ngrok tunnel.  
# If not defined, defaults to localhost.
urls = ngrok.get_public_urls()
SERVER_URL = urls[0] if len(urls) > 0 else None
SERVER_NAME = SERVER_URL[SERVER_URL.find('://') + 3 : ] if SERVER_URL else None
