# Twilio-AMD
Twilio's Answering Machine Detection is available for Outbound API calls only, so how do you forward an inbound call and handle the outbound leg with AMD?  The short answer is that you hold the inbound call in a conference or a queue, while making an Outbound API call.  

This example app, `forward_amd.py`, uses the [Flask](http://flask.pocoo.org/) Python web framework to show an inbound call being held in a conference while the outbound call is made.  You can find more about building Twilio apps with Flask [here](https://www.twilio.com/blog/2017/03/building-python-web-apps-with-flask.html).

## Installation
Clone or unzip this repository into your project directory.  If you're using a [Virtual Environment](https://virtualenv.pypa.io/en/stable/userguide/), do the following in your project directory:
```
virtualenv ENV
source ENV/bin/activate
```
Install the required Python libraries:
```
pip install requirements.txt
```
We're going to use an [Ngrok](https://ngrok.com/) tunnel to allow you to run the web app behind a firewall, which conveniently provides a public URL for Twilio's webhook requests:
```
ngrok http 5000
```
This command opens an HTTP tunnel to localhost port 5000:

<img width="579" alt="ngrok" src="https://user-images.githubusercontent.com/920404/32996073-f1481694-cd4b-11e7-81ea-3f8cf8af6860.png">

Make a note of one of the Ngrok URLs and use it to configure the webhook for the inbound calls:

<img width="753" alt="twilio" src="https://user-images.githubusercontent.com/920404/32996465-2ab8473c-cd51-11e7-827c-396956259db8.png">

## Configuring the App
The app configuration is stored in `config.py`.  It's here where you set your Twilio credentials, the server name, the forwarding number, and the caller id to use.  As a convenience, we call the Ngrok local API to discover the external URLs (HTTP and HTTPS) for the tunnel, and extract the server name from them.  

If you point your web browser to the `/index` URL, you can update the running configuration to set the called id and destination number:

<img width="326" alt="index" src="https://user-images.githubusercontent.com/920404/32999664-5f401384-cd71-11e7-9719-9e36cad6d39e.png">

Leaving the caller id blank will cause the app to use the incoming caller id.

## A Note on Caller Id
One important consideration is the handling of caller id.  Unlike forwarding a call using the `<Dial>` verb, you must specify the number to use as caller id.  Normally this has to be either a number in your Twilio account, or else a [Verified Caller Id](https://support.twilio.com/hc/en-us/articles/223180048-Adding-a-verified-outbound-caller-ID-with-Twilio).  However, for call flows such as this, you may ask your Twilio Customer Success Manager to enable the 'Any Caller Id Allowed' flag, and then you can use the caller id of the inbound call for the outbound leg.

## How the App Works
There are two principal URLs used by the app: `/incoming` for receiving the webhook from Twilio upon receiving an incoming call, and `/outgoing` for the callbacks from the outbound leg.  Rather than using the Twilio helper library to construct the TwiML responses, we have chosen to use static and template-based XML files.  (In this author's opinion, these make the call-handling logic clearer and easier to update.)

The `/incoming` webhook causes a conference to be created, named after the incoming call SID.  This is passed as a parameter to the outbound call's URL, so that the app does not have to maintain state.

The `/outgoing` callback has to handle a variety of different outcomes for the outbound call: no answer, failure and busy, in addition to being answered by a human or an answering machine.  It also handles the case when the caller has hung up: rather than connecting the called party to a conference with no-one there, our code checks to see whether there's an active conference named after the inbound call SID, and if not, disconnects the outbound call leg.
