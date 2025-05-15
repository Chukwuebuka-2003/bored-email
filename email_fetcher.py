import os
import base64
from datetime import datetime, timedelta
from typing import List, Optional
import email
from email.header import decode_header

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from models import EmailMessage, Config

# Alternative if you prefer using IMAP directly with app password
import imaplib
import email.parser

class EmailFetcher:
    """Fetches emails from Gmail using either Gmail API or IMAP"""
    
    def __init__(self, config: Config, use_api: bool = False):
        self.config = config
        self.use_api = use_api
        self.service = None
        
        if use_api:
            self._setup_gmail_api()
        
    def _setup_gmail_api(self):
        """Set up Gmail API credentials and service"""
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds = None
        
        # Load or refresh credentials
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
                
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        self.service = build('gmail', 'v1', credentials=creds)
    
    def fetch_recent_emails_api(self, hours_back: int) -> List[EmailMessage]:
        """Fetch emails from the past N hours using Gmail API"""
        if not self.service:
            raise ValueError("Gmail API service not initialized")
            
        # Calculate time N hours back from now
        time_back = datetime.now() - timedelta(hours=hours_back)
        query = f"after:{int(time_back.timestamp())}"
        
        # Get message list
        results = self.service.users().messages().list(
            userId='me', 
            q=query, 
            maxResults=self.config.max_emails_per_digest
        ).execute()
        
        messages = results.get('messages', [])
        email_messages = []
        
        for msg in messages:
            # Get full message details
            msg_details = self.service.users().messages().get(
                userId='me', 
                id=msg['id'], 
                format='full'
            ).execute()
            
            # Extract headers
            headers = msg_details['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'unknown')
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
            
            # Convert date string to datetime
            try:
                email_date = email.utils.parsedate_to_datetime(date_str)
            except:
                email_date = datetime.now()
            
            # Extract recipients
            to_field = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
            recipients = [addr.strip() for addr in to_field.split(',') if addr.strip()]
            
            # Extract body
            body = ""
            if 'parts' in msg_details['payload']:
                for part in msg_details['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body_data = part['body'].get('data', '')
                        if body_data:
                            body += base64.urlsafe_b64decode(body_data).decode('utf-8')
            else:
                # For simple messages
                body_data = msg_details['payload']['body'].get('data', '')
                if body_data:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8')
            
            # Create EmailMessage object
            email_messages.append(
                EmailMessage(
                    message_id=msg['id'],
                    sender=sender,
                    recipients=recipients,
                    subject=subject,
                    body=body,
                    date=email_date,
                    labels=msg_details.get('labelIds', [])
                )
            )
            
        return email_messages
    
    def fetch_recent_emails_imap(self, hours_back: int) -> List[EmailMessage]:
        """Alternative method to fetch emails using IMAP with app password"""
        emails = []
        
        # Connect to Gmail IMAP server
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(self.config.gmail_user, self.config.gmail_app_password)
        mail.select('inbox')
        
        # Calculate time N hours back from now
        time_back = datetime.now() - timedelta(hours=hours_back)
        date_string = time_back.strftime('%d-%b-%Y')
        
        # Search for emails
        status, messages = mail.search(None, f'(SINCE {date_string})')
        
        email_ids = messages[0].split()
        # Limit to max emails
        email_ids = email_ids[-min(len(email_ids), self.config.max_emails_per_digest):]
        
        parser = email.parser.BytesParser()
        
        for e_id in email_ids:
            # Fetch the email
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            
            for response in msg_data:
                if isinstance(response, tuple):
                    msg = parser.parsebytes(response[1])
                    
                    # Extract headers
                    subject = decode_header(msg['Subject'])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    
                    sender = msg['From']
                    date_str = msg['Date']
                    
                    # Convert date string to datetime
                    try:
                        email_date = email.utils.parsedate_to_datetime(date_str)
                    except:
                        email_date = datetime.now()
                    
                    # Extract recipients
                    recipients = [r.strip() for r in msg['To'].split(',')]
                    
                    # Extract body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    # Create EmailMessage object
                    emails.append(
                        EmailMessage(
                            message_id=e_id.decode(),
                            sender=sender,
                            recipients=recipients,
                            subject=subject,
                            body=body,
                            date=email_date
                        )
                    )
        
        mail.close()
        mail.logout()
        
        return emails
    
    def fetch_emails(self, hours_back: int) -> List[EmailMessage]:
        """Main method to fetch emails using either API or IMAP"""
        if self.use_api:
            return self.fetch_recent_emails_api(hours_back)
        else:
            return self.fetch_recent_emails_imap(hours_back)
