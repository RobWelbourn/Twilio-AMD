#!/usr/bin/env python

"""
Sets up Flask to simulate forwarding a call with answering machine detection.  An inbound
call is placed in a conference while an outbound API call is made to a target number.  If
an answering machine is detected, the call is terminated, a message is played to the inbound 
caller, and the inbound call is terminated.  If an answering machine is not detected, the
two calls are joined together in the conference.
"""

import json
import config
from flask import Flask, request, render_template, abort, url_for
from flask_socketio import SocketIO
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


CONTENT_XML = {'Content-Type': 'text/xml'}
client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
app = Flask(__name__)
socketio = SocketIO(app)
if config.SERVER_NAME:
    app.config['SERVER_NAME'] = config.SERVER_NAME

# Maintain a list of pending outbound calls, so we can cancel them 
# if the corresponding inbound calls are hung up prior to them being answered.
pending_calls = []


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    """Display the current setting for the Destination Number, 
    and update it if POSTed back.
    """
    if request.method == 'POST':
        config.dest_num = request.form.get('DestNum')
    return render_template('index.html', dest_num=config.dest_num)


@app.route('/inbound', methods=['POST'])
def inbound():
    """Respond to an inbound call by kicking off the outbound call, and parking the 
    inbound call in a conference named after the inbound call SID.
    """
    inbound_sid = request.values.get('CallSid')
    from_ = request.values.get('From')

    # If no caller id has been set in the configuration, let's attempt to use the caller
    # id of the inbound call.  Note that your account must have the 'Any Caller Id Allowed' 
    # flag enabled; please contact your Twilio Customer Success Manager if you need this.
    caller_id = config.CALLER_ID if config.CALLER_ID else from_
    url = url_for('outbound', InboundSid=inbound_sid, InboundCallerId=from_, _external=True)
    try:
        call = client.calls.create(
            to=config.dest_num,
            from_=caller_id,
            url=url,
            status_callback=url,
            machine_detection="Enable"
        )
    except TwilioRestException as ex:
        abort(500, ex.msg)

    update_dashboard(from_, "Dialing...")
    pending_calls.append(call.sid)
    action_url = url_for('inbound_ended', OutboundSid=call.sid,  _external=True)
    return render_template(
        'put_inbound_call_in_conf.xml', 
        action_url=action_url, 
        inbound_sid=inbound_sid
    ), CONTENT_XML


@app.route('/inbound_ended', methods=['POST'])
def inbound_ended():
    """Called when inbound call is hung up.  Check whether the 
    outbound call has yet been answered, and if not, cancel it.
    """
    outbound_sid = request.values.get('OutboundSid', None)
    if outbound_sid in pending_calls:
        pending_calls.remove(outbound_sid)
        app.logger.debug("Canceling outbound call %s", outbound_sid)

        try:
            client.calls(outbound_sid).update(status='canceled')
        except TwilioRestException as ex:
            app.logger.error(ex.msg)

    return app.send_static_file('hangup.xml'), CONTENT_XML


@app.route('/outbound', methods=['POST'])
def outbound():
    """Examine the callback from the outbound call leg and then:
    -- If it was answered by a machine, disconnect the call, inform the caller and hang up.
    -- If it was answered by a human, join the call to the conference.
    -- If the outbound call failed, got a busy signal or was not answered, inform the caller 
       and hang up.
    -- Otherwise, simply acknowledge the callback.
    """
    inbound_sid = request.values.get('InboundSid', None)
    outbound_sid = request.values.get('CallSid', None)
    inbound_caller_id = request.values.get('InboundCallerId', '')
    call_status = request.values.get('CallStatus', '')
    answered_by = request.values.get('AnsweredBy', '')

    if inbound_sid is None:
        abort(400, "Missing InboundSid")

    if outbound_sid in pending_calls:
        pending_calls.remove(outbound_sid)

    update_dashboard(inbound_caller_id, call_status, answered_by)

    if call_status == 'in-progress':
        if answered_by in {'machine_start', 'fax'}:
            modify_call(inbound_sid, 'not_available.xml')          
            return app.send_static_file('hangup.xml'), CONTENT_XML

        return render_template('put_outbound_call_in_conf.xml', inbound_sid=inbound_sid), CONTENT_XML

    if call_status in {'busy', 'failed', 'no-answer'}:
        modify_call(inbound_sid, 'not_available.xml')

    return '', 204        


def update_dashboard(caller_id, call_status, answered_by=None):
    """Use a WebSocket connection to update the browser dashboard on the call status."""
    if call_status == 'completed':
        return

    data = {}
    data['caller_id'] = caller_id
    if call_status == 'in-progress':
        if answered_by.startswith("machine"):
            data['call_status'] = "Answered by machine"
        else:
            data['call_status'] = "Answered by " + answered_by
    else:
        data['call_status'] = call_status

    json_data = json.dumps(data)
    socketio.emit('status update', json_data)


def modify_call(sid, twiml):
    """Modify a call."""
    try:
        client.calls(sid).update(
            url=url_for('static', filename=twiml, _external=True), 
            method='GET'
        )
    except TwilioRestException as ex:
        app.logger.warning("Unable to modify call: %s", ex.msg)  


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=True)
