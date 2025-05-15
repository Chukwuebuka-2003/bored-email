import os
import argparse
import logging
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from models import Config
from email_fetcher import EmailFetcher
from email_summarizer import EmailSummarizer
from email_composer import EmailComposer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("email_digest.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmailDigestApp:
    """Main application class that orchestrates the email digest process"""
    
    def __init__(self, env_path: str = ".env"):
        """Initialize the application with configuration from .env file"""
        self.config = self._load_config(env_path)
        self.fetcher = EmailFetcher(self.config)
        self.summarizer = EmailSummarizer(self.config)
        self.composer = EmailComposer(self.config)
        self.scheduler = BlockingScheduler()
    
    def _load_config(self, env_path: str) -> Config:
        """Load configuration from .env file"""
        try:
            # Try to load from .env file
            if os.path.exists(env_path):
                load_dotenv(env_path)
                logger.info(f"Loaded environment from {env_path}")
            else:
                load_dotenv()  # Try to load from default locations
                logger.info("Using environment variables")
            
            # Get team recipients as a list from comma-separated string
            team_recipients_str = os.getenv("TEAM_RECIPIENTS", "")
            team_recipients = [email.strip() for email in team_recipients_str.split(",") if email.strip()]
            
            return Config(
                gmail_user=os.getenv("GMAIL_USER"),
                gmail_app_password=os.getenv("GMAIL_APP_PASSWORD"),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                team_recipients=team_recipients,
                morning_cutoff_hours=int(os.getenv("MORNING_CUTOFF_HOURS", 12)),
                evening_cutoff_hours=int(os.getenv("EVENING_CUTOFF_HOURS", 12)),
                morning_schedule=os.getenv("MORNING_SCHEDULE", "0 7 * * *"),
                evening_schedule=os.getenv("EVENING_SCHEDULE", "0 21 * * *"),
                openai_model=os.getenv("OPENAI_MODEL", "gpt-4"),
                max_emails_per_digest=int(os.getenv("MAX_EMAILS_PER_DIGEST", 50))
            )
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            raise
    
    def process_morning_digest(self):
        """Process the morning email digest"""
        logger.info("Starting morning email digest process")
        
        try:
            # Fetch emails from the configured time period
            emails = self.fetcher.fetch_emails(self.config.morning_cutoff_hours)
            logger.info(f"Fetched {len(emails)} emails for morning digest")
            
            if not emails:
                logger.info("No emails to process for morning digest")
                return
            
            # Summarize emails
            summaries = self.summarizer.summarize_emails(emails)
            logger.info(f"Generated {len(summaries)} summaries for morning digest")
            
            # Create and send digest
            digest = self.composer.create_digest_report(summaries, "morning")
            success = self.composer.send_email(digest)
            
            if success:
                logger.info("Morning digest email sent successfully")
            else:
                logger.error("Failed to send morning digest email")
        
        except Exception as e:
            logger.error(f"Error processing morning digest: {str(e)}")
    
    def process_evening_digest(self):
        """Process the evening email digest"""
        logger.info("Starting evening email digest process")
        
        try:
            # Fetch emails from the configured time period
            emails = self.fetcher.fetch_emails(self.config.evening_cutoff_hours)
            logger.info(f"Fetched {len(emails)} emails for evening digest")
            
            if not emails:
                logger.info("No emails to process for evening digest")
                return
            
            # Summarize emails
            summaries = self.summarizer.summarize_emails(emails)
            logger.info(f"Generated {len(summaries)} summaries for evening digest")
            
            # Create and send digest
            digest = self.composer.create_digest_report(summaries, "evening")
            success = self.composer.send_email(digest)
            
            if success:
                logger.info("Evening digest email sent successfully")
            else:
                logger.error("Failed to send evening digest email")
        
        except Exception as e:
            logger.error(f"Error processing evening digest: {str(e)}")
    
    def schedule_jobs(self):
        """Schedule the morning and evening digest jobs"""
        # Schedule morning digest (7 AM)
        self.scheduler.add_job(
            self.process_morning_digest,
            CronTrigger.from_crontab(self.config.morning_schedule),
            id='morning_digest'
        )
        
        # Schedule evening digest (9 PM)
        self.scheduler.add_job(
            self.process_evening_digest,
            CronTrigger.from_crontab(self.config.evening_schedule),
            id='evening_digest'
        )
        
        logger.info(f"Scheduled morning digest: {self.config.morning_schedule}")
        logger.info(f"Scheduled evening digest: {self.config.evening_schedule}")
    
    def run_once(self, period: str = "morning"):
        """Run the digest process once for testing"""
        logger.info(f"Running {period} digest process once for testing")
        
        if period.lower() == "morning":
            self.process_morning_digest()
        elif period.lower() == "evening":
            self.process_evening_digest()
        else:
            logger.error(f"Invalid period: {period}. Must be 'morning' or 'evening'")
    
    def start(self):
        """Start the scheduler and run the application"""
        self.schedule_jobs()
        
        try:
            logger.info("Starting scheduler")
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")

def main():
    """Main entry point for the application"""
    parser = argparse.ArgumentParser(description="Email Digest Application")
    parser.add_argument("--env", default=".env", help="Path to .env configuration file")
    parser.add_argument("--run-once", action="store_true", help="Run once and exit (for testing)")
    parser.add_argument("--period", default="morning", choices=["morning", "evening"], 
                        help="Which digest to run when using --run-once")
    
    args = parser.parse_args()
    
    app = EmailDigestApp(args.env)
    
    if args.run_once:
        app.run_once(args.period)
    else:
        app.start()

if __name__ == "__main__":
    main()
