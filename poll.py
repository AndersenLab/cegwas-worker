import httplib2
import base64
import json
from apiclient import discovery
from oauth2client import client as oauth2client
from subprocess import check_output

PUBSUB_SCOPES = ['https://www.googleapis.com/auth/pubsub']

def create_pubsub_client(http=None):
    credentials = oauth2client.GoogleCredentials.get_application_default()
    if credentials.create_scoped_required():
        credentials = credentials.create_scoped(PUBSUB_SCOPES)
    if not http:
        http = httplib2.Http()
    credentials.authorize(http)

    return discovery.build('pubsub', 'v1', http=http)

client = create_pubsub_client()

# You can fetch multiple messages with a single API call.
batch_size = 1

subscription = 'projects/andersen-lab/subscriptions/cegwas-map'

# Create a POST body for the Pub/Sub request
body = {
    # Setting ReturnImmediately to false instructs the API to wait
    # to collect the message up to the size of MaxEvents, or until
    # the timeout.
    'returnImmediately': False,
    'maxMessages': batch_size,
}


while True:

    resp = client.projects().subscriptions().pull(
        subscription=subscription, body=body).execute()

    received_messages = resp.get('receivedMessages')
    if received_messages is not None:
        ack_ids = []
        for received_message in received_messages:
            pubsub_message = received_message.get('message')
            if pubsub_message:
                # Process messages
                message = base64.b64decode(str(pubsub_message.get('data')))
                # Get the message's ack ID
                ack_ids.append(received_message.get('ackId'))

        # Create a POST body for the acknowledge request
        ack_body = {'ackIds': ack_ids}

        # Acknowledge the message.
        client.projects().subscriptions().acknowledge(
            subscription=subscription, body=ack_body).execute()

        # Run workflow
        comm = """Rscript -e "library(knitr); knit('cegwas_output.Rmd')" --args '{message}'""".format(message = message)
        print comm
        check_output(comm)



