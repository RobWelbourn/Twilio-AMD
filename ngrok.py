"""
Module that gets the public Ngrok tunnel URLs by querying the local Ngrok API.
See https://ngrok.com/docs#client-api.
"""

import json
import urllib3

def get_public_urls():
    """Get a list of available external tunnel URLs"""
    urls = []

    try:
        http = urllib3.PoolManager()
        req = http.request('GET', 'http://localhost:4040/api/tunnels')
        data = str(req.data, 'utf-8')
        obj = json.loads(data)
        tunnels = obj['tunnels']
        for tunnel in tunnels:
            urls.append(tunnel['public_url'])
    except:
        # Ngrok not running.
        pass

    return urls

if __name__ == '__main__':
    print(get_public_urls())
