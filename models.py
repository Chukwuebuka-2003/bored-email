from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from datetime import datetime, timezone

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
    report_id: str = Field(default_factory=lambda: f"digest-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    period: str  # "morning" or "evening"
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    email_count: int
    high_priority_count: int
    summaries: List[EmailSummary]
    
class Config(BaseModel):
    """Application configuration"""
    gmail_user: EmailStr
    gmail_app_password: str
    team_recipients: List[EmailStr]
    morning_cutoff_hours: int = 12  # Hours to look back for morning report
    evening_cutoff_hours: int = 12  # Hours to look back for evening report
    morning_schedule: str = "0 7 * * *"  # 7 AM daily in cron format
    evening_schedule: str = "0 21 * * *"  # 9 PM daily in cron format
    max_emails_per_digest: int = 50

    # LLM settings. Defaults target a local LM Studio server (OpenAI-compatible
    # API) so no email content ever leaves your machine. To use a remote model,
    # set OPENAI_BASE_URL / OPENAI_API_KEY in your .env instead.
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = "lm-studio"  # LM Studio ignores this; used to satisfy the client
    openai_model: str = "local-model"
    llm_temperature: float = 0.2
    llm_timeout: int = 300  # seconds; local inference can be slow
