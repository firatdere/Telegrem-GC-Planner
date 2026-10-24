import os
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)


def create_event_with_meet(title: str, start_iso: str, end_iso: str, attendee_emails: list[str]) -> dict:
    service = get_calendar_service()

    event = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": "Europe/Istanbul"},
        "end": {"dateTime": end_iso, "timeZone": "Europe/Istanbul"},
        "attendees": [{"email": e} for e in attendee_emails],
        "conferenceData": {
            "createRequest": {
                "requestId": f"meet-{title[:20].replace(' ', '-')}-{start_iso[:10]}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 10},
            ],
        },
        "guestsCanModify": False,
        "guestsCanInviteOthers": False,
        "sendUpdates": "all",
    }

    created = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1,
        sendUpdates="all",
    ).execute()

    return created
