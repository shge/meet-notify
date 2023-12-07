import json
import os
import sys
import traceback
from base64 import b64decode

from dotenv import load_dotenv

load_dotenv()

import functions_framework
from cloudevents.http import CloudEvent
from google.apps import meet_v2beta as meet
from google.auth.transport import requests
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from slack import send_slack

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
SUBSCRIPTION_NAME = os.environ["SUBSCRIPTION_NAME"]
SPACE_NAME = os.environ["SPACE_NAME"]
MEETING_URL = os.environ["MEETING_URL"]


def authorize() -> Credentials:
    """Ensure valid credentials for calling the Meet API."""
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file("token.json")

    if credentials is None:
        flow = InstalledAppFlow.from_client_secrets_file(
            os.environ["CLIENT_SECRET_FILE"],
            scopes=[
                "https://www.googleapis.com/auth/meetings.space.created",
            ],
        )
        flow.run_local_server(port=0)
        credentials = flow.credentials

    if credentials and credentials.expired:
        credentials.refresh(requests.Request())

    if credentials is not None:
        with open("token.json", "w") as f:
            f.write(credentials.to_json())

    return credentials


USER_CREDENTIALS = authorize()


def create_space() -> meet.Space:
    """Create a new meeting space."""
    client = meet.SpacesServiceClient(credentials=USER_CREDENTIALS)
    request = meet.CreateSpaceRequest()
    return client.create_space(request=request)


def subscribe_to_space(space_name: str, topic_name: str):
    """Subscribe to events for a given meeting space."""
    session = requests.AuthorizedSession(USER_CREDENTIALS)
    body = {
        "targetResource": f"//meet.googleapis.com/{space_name}",
        "eventTypes": [
            # "google.workspace.meet.conference.v2.started",
            # "google.workspace.meet.conference.v2.ended",
            "google.workspace.meet.participant.v2.joined",
            "google.workspace.meet.participant.v2.left",
            # "google.workspace.meet.recording.v2.fileGenerated",
            # "google.workspace.meet.transcript.v2.fileGenerated",
        ],
        "payloadOptions": {
            "includeResource": False,
        },
        "notificationEndpoint": {"pubsubTopic": topic_name},
        # "ttl": "86400s", -> Possible max value
    }
    response = session.post(
        "https://workspaceevents.googleapis.com/v1beta/subscriptions", json=body
    )
    print(response.json())
    return response


def list_subscriptions(event_type: str):
    """List subscriptions for a given event type."""
    session = requests.AuthorizedSession(USER_CREDENTIALS)
    response = session.get(
        "https://workspaceevents.googleapis.com/v1beta/subscriptions",
        params={"filter": f'event_types:"{event_type}"'},
    )
    return response


def delete_subscription(subscription_name: str):
    """Delete a subscription."""
    session = requests.AuthorizedSession(USER_CREDENTIALS)
    response = session.delete(
        f"https://workspaceevents.googleapis.com/v1beta/{subscription_name}"
    )
    return response


def format_participant(participant: meet.Participant) -> str:
    """Formats a participant for display on the console."""
    if participant.anonymous_user:
        return f"{participant.anonymous_user.display_name} (Anonymous)"

    if participant.signedin_user:
        # return f"{participant.signedin_user.display_name} (ID: {participant.signedin_user.user})"
        return f"{participant.signedin_user.display_name}"

    if participant.phone_user:
        return f"{participant.phone_user.display_name} (Phone)"

    return "Unknown participant"


def fetch_participant_from_session(session_name: str) -> meet.Participant:
    """Fetches the participant for a given session."""
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    # Use the parent path of the session to fetch the participant details
    parsed_session_path = client.parse_participant_session_path(session_name)
    participant_resource_name = client.participant_path(
        parsed_session_path["conference_record"], parsed_session_path["participant"]
    )
    return client.get_participant(name=participant_resource_name)


def on_conference_started(payload: dict):
    """Display information about a conference when started."""
    resource_name = payload.get("conferenceRecord", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    conference = client.get_conference_record(name=resource_name)
    print(
        f"Conference (ID {conference.name}) started at {conference.start_time.rfc3339()}"
    )


def on_conference_ended(payload: dict):
    """Display information about a conference when ended."""
    resource_name = payload.get("conferenceRecord", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    conference = client.get_conference_record(name=resource_name)
    print(f"Conference (ID {conference.name}) ended at {conference.end_time.rfc3339()}")


def on_participant_joined(payload: dict):
    """Display information about a participant when they join a meeting."""
    resource_name = payload.get("participantSession", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    session = client.get_participant_session(name=resource_name)
    participant = fetch_participant_from_session(resource_name)
    display_name = format_participant(participant)
    print(f"{display_name} joined at {session.start_time.rfc3339()}")
    send_slack(f"{display_name} が参加しました: {MEETING_URL}")


def on_participant_left(payload: dict):
    """Display information about a participant when they leave a meeting."""
    resource_name = payload.get("participantSession", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    session = client.get_participant_session(name=resource_name)
    participant = fetch_participant_from_session(resource_name)
    display_name = format_participant(participant)
    print(f"{display_name} left at {session.end_time.rfc3339()}")
    send_slack(f"{display_name} が退出しました: {MEETING_URL}")


def on_recording_ready(payload: dict):
    """Display information about a recorded meeting when artifact is ready."""
    resource_name = payload.get("recording", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    recording = client.get_recording(name=resource_name)
    print(f"Recording available at {recording.drive_destination.export_uri}")


def on_transcript_ready(payload: dict):
    """Display information about a meeting transcript when artifact is ready."""
    resource_name = payload.get("transcript", {}).get("name")
    client = meet.ConferenceRecordsServiceClient(credentials=USER_CREDENTIALS)
    transcript = client.get_transcript(name=resource_name)
    print(f"Transcript available at {transcript.docs_destination.export_uri}")


def on_message(message: pubsub_v1.subscriber.message.Message | dict) -> None:
    """Handles an incoming event from pub/sub API."""
    # if type is <class 'google.cloud.pubsub_v1.subscriber.message.Message'>
    if isinstance(message, pubsub_v1.subscriber.message.Message):
        event_type = message.attributes.get("ce-type")
        subject = message.attributes.get("ce-subject")
        data_raw = message.data
        data = json.loads(data_raw)
    else:
        event_type = message.get("attributes", {}).get("ce-type")
        subject = message.get("attributes", {}).get("ce-subject")
        data_raw = b64decode(message.get("data", "")).decode("utf-8")
        data = json.loads(data_raw)

    print("event_type:", event_type)
    if not subject.endswith(SPACE_NAME):
        return

    handler = {
        "google.workspace.meet.conference.v2.started": on_conference_started,
        "google.workspace.meet.conference.v2.ended": on_conference_ended,
        "google.workspace.meet.participant.v2.joined": on_participant_joined,
        "google.workspace.meet.participant.v2.left": on_participant_left,
        "google.workspace.meet.recording.v2.fileGenerated": on_recording_ready,
        "google.workspace.meet.transcript.v2.fileGenerated": on_transcript_ready,
    }.get(event_type)

    try:
        if handler is not None:
            handler(data)
        try:
            message.ack()
            print("Message acknowledged.")
        except:
            pass
    except:
        print("Unable to process event:")
        traceback.print_exc()


@functions_framework.cloud_event
def subscribe(cloud_event: CloudEvent):
    print(cloud_event.data)
    message = cloud_event.data["message"]
    on_message(message)


SERVICE_CREDENTIALS = service_account.Credentials.from_service_account_file(
    os.environ["SERVICE_ACCOUNT_FILE"]
)


def listen_for_events(subscription_name: str):
    """Subscribe to events on the given subscription."""
    subscriber = pubsub_v1.SubscriberClient(credentials=SERVICE_CREDENTIALS)
    with subscriber:
        future = subscriber.subscribe(subscription_name, callback=on_message)
        print("Listening for events...")
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()
    print("Done")


def get_space(name: str):
    # Create a client
    client = meet.SpacesServiceClient(credentials=USER_CREDENTIALS)

    # Initialize request argument(s)
    request = meet.GetSpaceRequest(name=name)

    # Make the request
    response = client.get_space(request=request)

    # Handle the response
    return response


if __name__ == "__main__":
    listen_for_events(subscription_name=SUBSCRIPTION_NAME)
