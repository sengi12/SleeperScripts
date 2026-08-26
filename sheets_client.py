import os
import logging
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class SheetsClient:
    def __init__(self, credentials_path: str = 'credentials.json', token_path: str = 'token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        logging.basicConfig(level=logging.INFO)
        # Quiet the legacy discovery_cache INFO message from googleapiclient
        logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.WARNING)
        # cache the built service so we don't rebuild for every request
        self._service = None

    def _get_creds(self) -> Credentials:
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception as e:
                logging.warning(f"Failed to load {self.token_path}: {e}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as e:
                    logging.warning(f"Token refresh failed: {e}. Removing {self.token_path} and re-authorizing.")
                    try:
                        os.remove(self.token_path)
                    except OSError:
                        pass
                    creds = None
            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
        return creds

    def service(self):
        # Return a cached service if available (avoids repeated build() calls)
        if self._service is not None:
            return self._service
        creds = self._get_creds()
        # cache_discovery=False avoids use of the deprecated discovery cache
        # which prints: "file_cache is only supported with oauth2client<4.0.0"
        self._service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        return self._service

    def update_range(self, spreadsheet_id: str, range_name: str, values: List[List[Any]], value_input_option: str = 'USER_ENTERED') -> Dict[str, Any]:
        srv = self.service()
        body = {'values': values}
        return srv.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=range_name, valueInputOption=value_input_option, body=body).execute()

    def batch_update(self, spreadsheet_id: str, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        srv = self.service()
        body = {'valueInputOption': 'USER_ENTERED', 'data': data}
        return srv.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
