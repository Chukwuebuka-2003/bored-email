
import os
import base64
import logging
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger(__name__)

class EmailFetcher:
    """Fetches emails from Gmail using either Gmail API or IMAP"""
    
    def __init__(self, config: Config, use_api: bool = False):
        self.config = config
        self.use_api = use_api
        self.service = None
        
        if use_api:
            self._setup_gmail_api()
    
    def _decode_text(self, text_bytes, charset=None):
        """Try to decode text with multiple encodings"""
        if isinstance(text_bytes, str):
            return text_bytes
            
        # Try the specified charset first, then common fallbacks
        encodings = [charset] if charset else []
        encodings.extend(['utf-8', 'latin-1', 'iso-8859-1', 'windows-1252'])
        
        # Remove None values
        encodings = [enc for enc in encodings if enc]
        
        # Try each encoding
        for encoding in encodings:
            try:
                return text_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
                
        # If all failed, use replacement character for invalid bytes
        logger.warning(f"Failed to decode with all encodings, using 'replace' mode")
        return text_bytes.decode('utf-8', errors='replace')
        
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
    
    def _extract_email_body(self, msg):
        """Extract email body with proper encoding handling"""
        body = ""
        
        if msg.is_multipart():
            # Handle multipart messages
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                    
                # Get text content
                if content_type == "text/plain" or content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset()
                            body += self._decode_text(payload, charset)
                    except Exception as e:
                        logger.warning(f"Error decoding email part: {str(e)}")
                        # Continue to next part
        else:
            # Handle non-multipart messages
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset()
                    body = self._decode_text(payload, charset)
            except Exception as e:
                logger.warning(f"Error decoding email body: {str(e)}")
                
        return body
    
    def fetch_recent_emails_api(self, hours_back: int) -> List[EmailMessage]:
        """Fetch emails from the past N hours using Gmail API"""
        if not self.service:
            raise ValueError("Gmail API service not initialized")
            
        # Calculate time N hours back from now
        time_back = datetime.now(timezone.utc) - timedelta(hours=hours_back)
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
            try:
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
                    email_date = datetime.now(timezone.utc)
                
                # Extract recipients
                to_field = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
                recipients = [addr.strip() for addr in to_field.split(',') if addr.strip()]
                
                # Extract body
                body = ""
                try:
                    if 'parts' in msg_details['payload']:
                        for part in msg_details['payload']['parts']:
                            if part['mimeType'] == 'text/plain':
                                body_data = part['body'].get('data', '')
                                if body_data:
                                    decoded_bytes = base64.urlsafe_b64decode(body_data)
                                    body += self._decode_text(decoded_bytes)
                    else:
                        # For simple messages
                        body_data = msg_details['payload']['body'].get('data', '')
                        if body_data:
                            decoded_bytes = base64.urlsafe_b64decode(body_data)
                            body += self._decode_text(decoded_bytes)
                except Exception as e:
                    logger.warning(f"Error extracting body from email {msg['id']}: {str(e)}")
                
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
            except Exception as e:
                logger.error(f"Error processing email {msg['id']}: {str(e)}")
                # Continue with the next email
            
        return email_messages
    
    def fetch_recent_emails_imap(self, hours_back: int) -> List[EmailMessage]:
        """Alternative method to fetch emails using IMAP with app password"""
        emails = []
        
        try:
            # Connect to Gmail IMAP server
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(self.config.gmail_user, self.config.gmail_app_password)
            mail.select('inbox')
            
            # Calculate time N hours back from now
            time_back = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            date_string = time_back.strftime('%d-%b-%Y')
            
            # Search for emails
            status, messages = mail.search(None, f'(SINCE {date_string})')
            
            if status != "OK":
                logger.error("Failed to search for emails")
                return emails
                
            email_ids = messages[0].split()
            
            # Limit to max emails
            if not email_ids:
                logger.info("No emails found in the specified time range")
                return emails
                
            email_ids = email_ids[-min(len(email_ids), self.config.max_emails_per_digest):]
            
            for e_id in email_ids:
                try:
                    # Fetch the email
                    status, msg_data = mail.fetch(e_id, '(RFC822)')
                    
                    if status != "OK":
                        logger.warning(f"Failed to fetch email with ID {e_id}")
                        continue
                    
                    for response in msg_data:
                        if not isinstance(response, tuple):
                            continue
                            
                        # Parse the email
                        msg = email.message_from_bytes(response[1])
                        
                        # Extract and decode subject
                        subject = ""
                        subject_header = msg['Subject']
                        if subject_header:
                            for decoded_text, charset in decode_header(subject_header):
                                if isinstance(decoded_text, bytes):
                                    subject += self._decode_text(decoded_text, charset)
                                else:
                                    subject += str(decoded_text)
                        
                        # Extract sender
                        sender = msg['From']
                        
                        # Convert date string to datetime
                        date_str = msg['Date']
                        try:
                            email_date = email.utils.parsedate_to_datetime(date_str)
                        except:
                            email_date = datetime.now(timezone.utc)
                        
                        # Extract recipients
                        to_header = msg['To']
                        recipients = []
                        if to_header:
                            recipients = [r.strip() for r in to_header.split(',') if r.strip()]
                        
                        # Extract body with encoding handling
                        body = self._extract_email_body(msg)
                        
                        # Extract attachments
                        attachments = []
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_disposition = part.get("Content-Disposition")
                                if content_disposition and "attachment" in content_disposition:
                                    filename = part.get_filename()
                                    if filename:
                                        attachments.append(filename)
                        
                        # Create EmailMessage object
                        email_obj = EmailMessage(
                            message_id=e_id.decode(),
                            sender=sender,
                            recipients=recipients,
                            subject=subject,
                            body=body,
                            date=email_date,
                            attachments=attachments
                        )
                        
                        emails.append(email_obj)
                        break  # Only process the first part of the response
                        
                except Exception as e:
                    logger.error(f"Error processing email {e_id}: {str(e)}")
                    # Continue with the next email
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"Error in IMAP email fetching: {str(e)}")
            
        return emails
    
    def fetch_emails(self, hours_back: int) -> List[EmailMessage]:
        """Main method to fetch emails using either API or IMAP"""
        try:
            if self.use_api:
                return self.fetch_recent_emails_api(hours_back)
            else:
                return self.fetch_recent_emails_imap(hours_back)
        except Exception as e:
            logger.error(f"Error fetching emails: {str(e)}")
            return []