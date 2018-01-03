# Twilio-AMD
Twilio's Answering Machine Detection (AMD) was designed to work with Outbound API calls, but not with calls forwarded using the `<Dial>` verb.  That being so, how do you forward a call *and* make use of AMD?  The short answer is that you hold the inbound call in a conference or a queue, while making an Outbound API call.  

We present two sample apps, `forward_amd.py` and `tr_with_amd.py`, that respectively make use of a conference and a queue to hold the inbound call leg while making the outbound call.  The latter also uses a simple TaskRouter configuration to select an agent to whom a call should be forwarded.

Both samples use the [Flask](http://flask.pocoo.org/) Python server-side framework to provide a simple web interface and the HTTP webhooks called by Twilio.  You can find more about building Twilio apps with Flask [here](https://www.twilio.com/blog/2017/03/building-python-web-apps-with-flask.html).  We've also made use of the [Socket.IO](https://socket.io/) JavaScript library and the corresponding [Flask extension](https://blog.miguelgrinberg.com/post/easy-websockets-with-flask-and-gevent) for WebSockets to provide call dashboards that auto-update in real time.

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

![ngrok tunnel](https://user-images.githubusercontent.com/920404/32996073-f1481694-cd4b-11e7-81ea-3f8cf8af6860.png)

Make a note of one of the Ngrok URLs and use it to configure the webhook for the inbound calls, using the path  `/inbound`:

![twilio config](https://user-images.githubusercontent.com/920404/32996465-2ab8473c-cd51-11e7-827c-396956259db8.png)

Be aware that if you're using the free version of Ngrok, then the tunnel URL will change each time you run the `ngrok` command.

## Configuring the Apps
Both apps store their configurations in `config.py`.  It's here where you set your Twilio credentials, the server name, the caller id to use, the forwarding number (for `forward_amd.py`), and the TaskRouter workspace name (for `tr_with_amd.py`).   

Some configuration information can be extracted from the environment.  We recommend creating the local environment variables `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` to hold your account information, which the configuration module uses by default.  As a convenience, we call the Ngrok local API to discover the external URLs (HTTP and HTTPS) for the tunnel, and extract the server name from them. 

For both apps, leaving the caller id blank will cause the app to use the caller id of the incoming call (but see the note below).  For `forward_amd.py`, you can set the default destination number to which calls will be forwarded.  This number can also be updated from the application dashboard.  For `tr_with_amd.py`, forwarding numbers are associated with the agents defined in the TaskRouter configuration, which is described later.

### A Note on Caller Id
One important consideration is the handling of caller id.  Unlike forwarding a call using the `<Dial>` verb, you must specify the number to use as caller id.  Normally this has to be either a number in your Twilio account, or else a [Verified Caller Id](https://support.twilio.com/hc/en-us/articles/223180048-Adding-a-verified-outbound-caller-ID-with-Twilio).  However, for call flows such as this, you may ask your Twilio Customer Success Manager to enable the 'Any Caller Id Allowed' flag, and then you can use the caller id of the inbound call for the outbound leg.

## Forwarding with AMD (`forward_amd.py`)
The app home page (`/` or `/index`) provides a dashboard of call progress and allows you to set the destination of a call: 

![Forward-AMD](https://user-images.githubusercontent.com/920404/34496545-ef817b40-efc7-11e7-9653-cc25a81bea4e.png)

There are two principal URLs used by the app: `/incoming`, the webhook from Twilio upon receiving an incoming call, and `/outgoing` for the callbacks from the outbound leg.  Rather than using the Twilio helper library to construct the TwiML responses, we have chosen to use static and template-based XML files.  

The `/incoming` webhook causes a conference to be created, named after the incoming call SID.  This is passed as a parameter to the outbound call's URL, so that it can conveniently be retrieved when the call is answered.

The `/outgoing` callback has to handle a variety of different outcomes for the outbound call: no answer, failure and busy, in addition to being answered by a human, a fax machine or an answering machine.  

We maintain a list of pending outbound calls, in case they need to be canceled if the caller hangs up before the outbound call in answered.  Once the call is answered, we remove it from the pending list; if the inbound call is hung up while waiting for an answer, the presence of the outbound call SID in the pending list indicates that it needs to be canceled.  

### The Call Status Dashboard
The call status dashboard makes use of jQuery and Socket.IO to communicate updates from Flask to the browser.  Updates to the caller id and call status are packaged up as JSON objects at the server and displayed in the browser.  The final disposition of the call is displayed when the call is hung up.

## TaskRouter with AMD (`tr_with_amd.py`)
### Configuring TaskRouter
[TaskRouter](https://www.twilio.com/docs/api/taskrouter) at its heart is an engine for allocating tasks among a pool of workers by matching the requirements of the task with the capabilities and availability of the worker.  It is typically used to match inbound calls in a contact center to an agent, based on the caller's choice (for example, selecting 'Sales' or 'Support' from an IVR menu) and the skills of the worker (for example, languages spoken).  

TaskRouter can be configured entirely through its REST API, but in this case we're going to set it up through the Twilio Console.  Login to the Console, and navigate to TaskRouter > Workspaces > Create New Workspace.  A workspace is the container for everything related to [Workflows](https://www.twilio.com/docs/api/taskrouter/workflow-configuration), [Tasks](https://www.twilio.com/docs/api/taskrouter/tasks), [Workers](https://www.twilio.com/docs/api/taskrouter/workers) and their skills, and the various [Activity](https://www.twilio.com/docs/api/taskrouter/activities) states that a worker can be in.

![Define workspace](https://user-images.githubusercontent.com/920404/34508443-67b38cda-f00d-11e7-8ebd-1a6d47d94115.png)

To initialize the workspace, give it a name (we suggest "AMD"), set the event callback URL to your server with the path `/trevents`, and check all the event boxes.  Strictly speaking, we only need the worker activity update and task cancellation events, but it is instructive to see a debug log of all the events that TaskRouter processes.  Be aware that a production TaskRouter implementation generates a *huge* number of events, so you may not want to do this on a production system.  Click 'Save' when done.

Next, we'll set up a new TaskQueue to handle the inbound calls.  Give it an appropriate name and click 'Save'.

Next, we'll create a Workflow that will place calls in the queue.  Give it a descriptive name, set the task assignment callback URL to your server with the path `/assign`, set an assignment timeout value (we've chosen 120 seconds), accept the choice of the single queue you created in the previous step, and then click 'Save':

![workflow](https://user-images.githubusercontent.com/920404/34508926-df92f90c-f012-11e7-9a47-ed81144bf731.png)

Next, we're going to need some workers (that is, agents) who are going to receive calls.  In this case, the most important thing to know about the worker is their phone number, so we're going to define an attribute `phone` along with its value, an international-format phone number. The workers' attributes are formatted as JSON:

![worker](https://user-images.githubusercontent.com/920404/34509157-b33b114e-f014-11e7-8457-17ed09fe73da.png)

You can ignore the Task Channels assignments, and note that the worker is automatically assigned to the TaskQueue we defined earlier.

Repeat this step for as many workers as you like.

Finally, we're going to customize the activity states a worker can be in.  In addition to the standard *Offline*, *Idle*, *Busy* and *Reserved* states, we're going to define one called *Temporarily Unavailable*.  This is used when we want to prevent TaskRouter from trying to assign a task to a worker who was recently busy, so they are not being constantly dialed in situations where few agents are available:

![temporarily unavailable](https://user-images.githubusercontent.com/920404/34509429-b13d3770-f017-11e7-8c6c-51b738a8b71c.png)

Now that the configuration of TaskRouter is finished, make sure the workspace name in the `config.py` file is identical to the one you have just created.

### How `tr_with_amd.py` Works
Inbound calls result in a webhook to the app's `/incoming` URL, returning TwiML that enqueues the call in a TaskQueue.  We store the incoming caller id in the task attributes.  

Next, TaskRouter reserves a worker based on their availability (by default, the least recently used worker is chosen) and makes an assignment callback to the app's `/assign` URL, providing information about the task and the selected worker.  This causes an Outbound API call to be made to the worker's phone number.  The task and reservation details are embedded in the callback URL.

When the call is answered, we examine whether or not an answering machine was detected.  If yes, the reservation is rejected and the outbound call is hung up.  If not, we dial the queue to join the two call legs together.

If the call fails, is not answered or the agent is busy, we reject the reservation.  If the reservation is rejected, TaskRouter moves on to the next available worker.

In most situations, we set the worker's next state to be *Temporarily Unavailable*.  This prevents TaskRouter from trying to call a number repeatedly when, for example, an answering maching is detected and there are no other workers available to handle calls.  After a configurable period of time (determined by `config.TEMP_UNAVAILABLE_TIMER`), we set the worker back to *Idle*.

If the inbound caller hangs up prior to the reservation being accepted, TaskRouter will cancel the task.  We react to a cancelled task by cancelling the outbound call to the worker.  Similar to `forward_amd.py`, we use a dictionary of pending outbound calls, in this case indexed by the task SID.

### The Agent Dashboard
The app home page (`/` or `/index`) provides an agent dashboard, displaying agent status:

![Agent Dashboard](https://user-images.githubusercontent.com/920404/34535690-b4ad351c-f090-11e7-8a38-eea917312c5e.png)

The dashboard uses jQuery and Socket.IO to receive and display status updates for the agents over a WebSocket connection.  The dashboard is also used to set agents online and offline, using the WebSocket to send that information to the server and thence to TaskRouter.  The agent status is highlighted using a CSS class that corresponds to the name of the agent's activity state.