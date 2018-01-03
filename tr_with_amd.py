#!/usr/bin/env python

"""
Sets up Flask to simulate forwarding a call with answering machine detection, using a queue
and TaskRouter.  An inbound call is enqueued, and TaskRouter reserves a worker to whom the
outbound call should be made.  The app responds to the reservation by dialing the worker.  If
an answering machine is detected, the call is terminated and the reservation cancelled.  At this
point another worker may be reserved, or the inbound call disconnected with a message.  If an 
answering machine is not detected, then the reservation is accepted and the worker is joined
to the queue.
"""

import sys
import json
import config
from threading import Timer
from flask import Flask, request, render_template, abort, url_for
from flask_socketio import SocketIO
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


class Agent:
    """Struct for an agent."""
    def __init__(self, worker):
        self.sid = worker.sid
        self.name = worker.friendly_name 
        self.activity_sid = worker.activity_sid
        self.activity_name = worker.activity_name
        self.online = worker.activity_name != "Offline"
        try:
            self.phone = json.loads(worker.attributes)['phone']
        except KeyError:
            self.phone = ""


class Workspace:
    """Essential information about a TaskRouter workspace, derived from its name."""
    def __init__(self, name):
        ws_list = client.taskrouter.workspaces.list(friendly_name=name)

        if not ws_list:
            raise ValueError("Error: no workspace named {}".format(name))

        self.sid = ws_list[0].sid
        workflows = ws_list[0].workflows.list()
        activities = ws_list[0].activities.list()

        if not workflows:
            raise IndexError("Error: workspace {} contains no workflows".format(name))
        
        self.workflow_sid = workflows[0].sid
        self.activity_names = {}
        self.activity_sids = {}
        for activity in activities:
            self.activity_names[activity.sid] = activity.friendly_name
            self.activity_sids[activity.friendly_name] = activity.sid
            

CONTENT_XML = {'Content-Type': 'text/xml'}
CONTENT_JSON = {'Content-Type': 'application/json'}

# Initialize Flask.
app = Flask(__name__)
socketio = SocketIO(app)
if config.SERVER_NAME:
    app.config['SERVER_NAME'] = config.SERVER_NAME

# Maintain a dictionary of pending outbound calls, keyed on the Task SID, 
# so we can cancel them if the corresponding tasks are cancelled.
pending_calls = {}

# Initialize Twilio Client object, and get essential info about our TaskRouter workspace.
try:
    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    workspace = Workspace(config.WORKSPACE_NAME)
    activity_offline = workspace.activity_sids['Offline']
    activity_idle = workspace.activity_sids['Idle']
    activity_temp_unavailable = workspace.activity_sids['Temporarily Unavailable']
except TwilioRestException as ex:
    sys.exit(ex.msg)
except KeyError as ex:
    sys.exit("Error: missing activity {}".format(str(ex)))
except Exception as ex:
    sys.exit(str(ex))


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    """Display the Agent Dashboard, showing agents' phone numbers and status."""
    agents = []
    try:
        workers = client.taskrouter.workspaces(workspace.sid).workers.list()
        for worker in workers:
            agents.append(Agent(worker))

    except TwilioRestException as ex:
        abort(500, ex.msg)

    return render_template('index2.html', agents=agents)


@app.route('/inbound', methods=['POST'])
def incoming():
    """Respond to an inbound call by enqueuing it."""
    caller_id = request.values.get('From')
    return render_template(
        'enqueue_call.xml', 
        workflow_sid=workspace.workflow_sid, 
        caller_id=caller_id
    ), CONTENT_XML


@app.route('/trevents', methods=['POST'])
def trevents():
    """Webhook for TaskRouter events.  Handle worker update
    and task cancellation events."""
    description = request.values.get('EventDescription', '')
    event_type = request.values.get('EventType', None)
    app.logger.debug("Event: %s", description)

    if event_type == 'worker.activity.update':
        update_dashboard()

    elif event_type == 'task.canceled':
        cancel_call()

    return '', 204


def update_dashboard():
    """Send agent updates to the web browser."""
    data = {}
    data['worker_sid'] = request.values.get('WorkerSid', '')
    data['worker_name'] = request.values.get('WorkerName', '')
    data['activity_sid'] = request.values.get('WorkerActivitySid', '')
    data['activity_name'] = request.values.get('WorkerActivityName', '')
    data['previous_activity_name'] = \
        workspace.activity_names[request.values.get('WorkerPreviousActivitySid', '')]
    json_data = json.dumps(data)
    socketio.emit('status update', json_data)


def cancel_call():
    """Cancel an outbound call leg, if one is in progress."""
    task_sid = request.values.get('TaskSid')
    if task_sid in pending_calls:
        try:
            call_sid = pending_calls[task_sid]
            app.logger.debug("Canceling outbound call %s for task %s", call_sid, task_sid)
            client.calls(call_sid).update(status='canceled')
        except TwilioRestException as ex:
            app.logger.error(ex.msg)


@socketio.on('status update')
def process_update(status_update):
    """Update the agent's status based on an update from the browser dashboard."""
    app.logger.debug("Update: %s", status_update)
    try:
        client.taskrouter.workspaces(workspace.sid).workers(status_update['worker_sid']).update(
            activity_sid = activity_idle if status_update['online'] else activity_offline
        )
    except TwilioRestException as ex:
        app.logger.error("Couldn't update worker status: %s", ex.msg)


@app.route('/assign', methods=['POST'])
def assign():
    """TaskRouter assignment callback.  Kick off the outbound 
    API call and return an interim acknowledgement response."""
    worker_attributes = json.loads(request.values.get('WorkerAttributes'))
    task_attributes = json.loads(request.values.get('TaskAttributes'))
    reservation_sid = request.values.get('ReservationSid')
    task_sid = request.values.get('TaskSid')
    worker_sid = request.values.get('WorkerSid')

    # Make sure we have a phone number to call.  If not, reject the reservation, 
    # and put the worker offline.
    try:
        phone = worker_attributes['phone']
    except KeyError:
        response = '{{ "instruction":"reject", "activity_sid":"{}" }}'.format(activity_offline)
        return response, CONTENT_JSON

    # Pick the caller id to use for the outbound call.
    caller_id = config.CALLER_ID if config.CALLER_ID else task_attributes['caller_id']

    try:
        # Initiate the call, and make a note of it in the pending calls dictionary.
        url = url_for(
            'outbound', 
            TaskSid=task_sid, 
            ReservationSid=reservation_sid,
            WorkerSid=worker_sid,
            _external=True
        )
        call = client.calls.create(
            to=phone,
            from_=caller_id,
            url=url,
            status_callback=url,
            machine_detection="Enable"
        )
        pending_calls[task_sid] = call.sid
    except TwilioRestException as ex:
        abort(500, ex.msg)
    
    return '', 204


@app.route('/outbound', methods=['POST'])
def outbound():
    """Examine the callback from the outbound call leg and then:
    -- If it was answered by a machine, reject the TaskRouter reservation and hang up.
    -- If it was answered by a human, dial the queue.
    -- If the outbound call failed, got a busy signal or was not answered, 
       reject the reservation.
    -- Otherwise, simply acknowledge the callback.
    """
    task_sid = request.values.get('TaskSid', None)
    reservation_sid = request.values.get('ReservationSid', None)
    worker_sid = request.values.get('WorkerSid', None)
    call_sid = request.values.get("CallSid")
    call_status = request.values.get('CallStatus')
    answered_by = request.values.get('AnsweredBy', None)

    app.logger.debug(
        "Call SID=%s, Task SID=%s, status=%s, answered by=%s",
        call_sid, task_sid, call_status, answered_by
    )

    if task_sid in pending_calls:
        pending_calls.pop(task_sid)

    if call_status in {'completed', 'canceled'}:
        return '', 204

    if task_sid is None:
        abort(400, "Missing TaskSid")
    if reservation_sid is None:
        abort(400, "Missing ReservationSid")
    if worker_sid is None:
        abort(400, "Missing WorkerSid")

    if call_status == 'in-progress':
        if answered_by == 'machine_start':
            reject_reservation(task_sid, reservation_sid, activity_temp_unavailable)
            Timer(config.TEMP_UNAVAILABLE_TIMER, reschedule_agent, [worker_sid]).start()
            return app.send_static_file('hangup.xml'), CONTENT_XML

        # Dialing the queue with the Reservation SID implicitly accepts the reservation.  We
        # set the post-work activity SID to 'Temporarily Unavailable', and then start a timer to 
        # put the agent in 'Idle' state so they can accept more calls after this one has ended.
        Timer(config.TEMP_UNAVAILABLE_TIMER, reschedule_agent, [worker_sid]).start()
        return render_template(
            'dial_queue.xml', 
            reservation_sid=reservation_sid,
            activity_sid=activity_temp_unavailable
        ), CONTENT_XML

    # If the call failed, set the agent to offline, as it's likely there was 
    # some issue with the phone number.
    if call_status == 'failed':
        reject_reservation(task_sid, reservation_sid, activity_offline)
        return '', 204

    # For any other response (notably busy, no answer), simply reject the reservation,
    # and temporarily prevent TaskRouter from re-assigning to the worker.
    reject_reservation(task_sid, reservation_sid, activity_temp_unavailable)
    Timer(config.TEMP_UNAVAILABLE_TIMER, reschedule_agent, [worker_sid]).start()
    return '', 204


def reject_reservation(task_sid, reservation_sid, activity):
    """Reject a task reservation and set the worker activity."""
    try:
        client.taskrouter.workspaces(workspace.sid) \
            .tasks(task_sid).reservations(reservation_sid) \
            .update(reservation_status="rejected", worker_activity_sid=activity)
    except TwilioRestException as ex:
        app.logger.warning("Unable to update task reservation: %s", ex.msg)


def reschedule_agent(worker_sid):   
    """Put a worker back into Idle state."""
    try:
        app.logger.debug("Rescheduling agent %s", worker_sid)
        client.taskrouter.workspaces(workspace.sid) \
            .workers(worker_sid).update(activity_sid=activity_idle)
    except TwilioRestException as ex:
        app.logger.warning("Unable to update worker activity: %s", ex.msg)    


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=True)
