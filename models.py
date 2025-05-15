from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from datetime import datetime

class EmailMessage(BaseModel):
    """Represents a single email message"""
    message_id: str
    sender: EmailStr
    recipients: List[EmailStr]
    subject: str
    body: str
    date: datetime
    labels: Optional[List[str]] = []
    attachments: Optional[List[str]] = []

class EmailSummary(BaseModel):
    """Represents the AI-generated summary of an email"""
    message_id: str
    sender: EmailStr
    subject: str
    key_points: List[str] = Field(..., description="Main points from the email")
    action_items: List[str] = Field(..., description="Required actions from the email")
    priority: str = Field(..., description="High/Medium/Low priority classification")
    date: datetime
    
class DigestReport(BaseModel):
    """Represents the compiled digest of email summaries"""
    report_id: str = Field(default_factory=lambda: f"digest-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    period: str  # "morning" or "evening"
    date: datetime = Field(default_factory=datetime.now)
    email_count: int
    high_priority_count: int
    summaries: List[EmailSummary]
    
class Config(BaseModel):
    """Application configuration"""
    gmail_user: EmailStr
    gmail_app_password: str
    openai_api_key: str
    team_recipients: List[EmailStr]
    morning_cutoff_hours: int = 12  # Hours to look back for morning report
    evening_cutoff_hours: int = 12  # Hours to look back for evening report
    morning_schedule: str = "0 7 * * *"  # 7 AM daily in cron format
    evening_schedule: str = "0 21 * * *"  # 9 PM daily in cron format
    openai_model: str = "gpt-4"
    max_emails_per_digest: int = 50
