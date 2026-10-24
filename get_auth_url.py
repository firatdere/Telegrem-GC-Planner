import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES,
    redirect_uri="urn:ietf:wg:oauth:2.0:oob"
)

auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
print("\n=== Bu URL'yi tarayıcınızda açın ===")
print(auth_url)
print("\nİzin verdikten sonra gelen kodu buraya yapıştırın:")
code = input("Kod: ").strip()

flow.fetch_token(code=code)
creds = flow.credentials

with open("token.pickle", "wb") as f:
    pickle.dump(creds, f)

print("\n✅ token.pickle oluşturuldu!")
