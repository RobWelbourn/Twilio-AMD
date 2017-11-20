#!/usr/bin/env python

"""
Sets up Flask to simulate forwarding a call with answering machine detection.  An inbound
call is placed in a conference while an outbound API call is made to a target number.  If
an answering machine is detected, the call is terminated, a message is played to the inbound 
caller, and the inbound call is terminated.  If an answering machine is not detected, the
two calls are joined together in the conference.
"""

import config
from flask import Flask, request, render_template, abort, url_for
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
app = Flask(__name__)
if config.SERVER_NAME:
    app.config['SERVER_NAME'] = config.SERVER_NAME


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    """Display the current settings for Caller Id and Destination Number, 
    and update them if they were POSTed back.
    """
    if request.method == 'POST':
        config.caller_id = request.form.get('CallerId')
        config.dest_num = request.form.get('DestNum')
    return render_template('index.html', caller_id=config.caller_id, dest_num=config.dest_num)


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
    caller_id = config.caller_id if config.caller_id else from_
    try:
        call = client.calls.create(
            to=config.dest_num,
            from_=caller_id,
            url=url_for('outbound', InboundSid=inbound_sid, _external=True),
            status_callback=url_for('outbound', InboundSid=inbound_sid, _external=True),
            machine_detection="Enable"
        )
    except TwilioRestException as ex:
        abort(500, ex.msg)

    return render_template('put_call_in_conf.xml', inbound_sid=inbound_sid), \
        {'Content-Type': 'text/xml'}


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
    outbound_sid = request.values.get('CallSid')
    call_status = request.values.get('CallStatus')
    answered_by = request.values.get('AnsweredBy', None)
    if inbound_sid is None:
        abort(400, "Missing InboundSid")

    if call_status == 'in-progress':
        if answered_by == 'machine_start':
            modify_call(inbound_sid, 'not_available.xml')          
            return app.send_static_file('hangup.xml'), {'Content-Type': 'text/xml'}

        else:
            if conference_is_active(inbound_sid):
                return render_template('put_call_in_conf.xml', inbound_sid=inbound_sid), \
                    {'Content-Type': 'text/xml'}
            else:
                return app.send_static_file('hangup.xml'), {'Content-Type': 'text/xml'}

    elif call_status in {'busy', 'failed', 'no-answer', 'canceled'}:
        modify_call(inbound_sid, 'not_available.xml')
        return '', 204

    return '', 204        


def modify_call(sid, twiml):
    """Modify a call."""
    try:
        client.calls(sid).update(
            url=url_for('static', filename=twiml, _external=True), 
            method='GET'
        )
    except TwilioRestException as ex:
        app.logger.warning("Unable to modify call: %s", ex.msg)  


def conference_is_active(name):
    """Is the named conference active?"""
    try:
        conferences = client.conferences.list(status="in-progress", friendly_name=name)
        return len(conferences) > 0
    except TwilioRestException as ex:
        app.logger.warning("Can't find conference %s: %s", name, ex.msg)
        return False


app.run(host='0.0.0.0', port=config.PORT, debug=True)
