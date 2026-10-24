"""
Run this script once to authorize Google Calendar access.
It will open a browser window, ask you to log in and grant permission,
then save the token to token.pickle for future use.
"""

from calendar_service import get_calendar_service

if __name__ == "__main__":
    service = get_calendar_service()
    print("✅ Google Calendar yetkisi başarıyla alındı. token.pickle oluşturuldu.")
    cal = service.calendarList().get(calendarId="primary").execute()
    print(f"   Takvim: {cal.get('summary')} ({cal.get('id')})")
