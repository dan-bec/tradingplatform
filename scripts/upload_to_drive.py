import os
import pickle
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Set up logging
logging.basicConfig(level=logging.INFO)

# Google Drive API scope
SCOPES = ['https://www.googleapis.com/auth/drive']

def authenticate_google_drive(credentials_path):
    """Authenticate with Google Drive API and return the service object."""
    creds = None
    # Load existing token if it exists
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # Check if credentials are valid or need refreshing
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Credentials refreshed successfully.")
            except Exception as e:
                logging.error(f"Failed to refresh credentials: {e}")
                creds = None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                logging.info("New credentials obtained successfully.")
            except Exception as e:
                logging.error(f"Failed to authenticate: {e}")
                creds = None
        
        # Save new credentials if obtained
        if creds:
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
    
    # Build and return service object, or None if authentication failed
    if creds:
        return build('drive', 'v3', credentials=creds)
    else:
        logging.error("Authentication failed. Check credentials file and API settings.")
        return None

def create_folder(service, name, parent_id):
    """Create a folder in Google Drive."""
    if service is None:
        logging.error("Cannot create folder: service is None.")
        return None
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')