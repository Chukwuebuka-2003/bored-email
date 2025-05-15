import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List

from models import EmailSummary, DigestReport, Config

class EmailComposer:
    """Composes and sends email digests"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def create_digest_report(self, summaries: List[EmailSummary], period: str) -> DigestReport:
        """Create a digest report from email summaries"""
        high_priority_count = sum(1 for summary in summaries if summary.priority == "High")
        
        return DigestReport(
            period=period,
            email_count=len(summaries),
            high_priority_count=high_priority_count,
            summaries=summaries
        )
    
    def format_html_email(self, digest: DigestReport) -> str:
        """Format the digest as HTML email"""
        period_name = "Morning" if digest.period == "morning" else "Evening"
        today = digest.date.strftime("%A, %B %d, %Y")
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .header {{ padding: 20px; background-color: #f5f5f5; border-bottom: 1px solid #ddd; }}
                .summary {{ margin-bottom: 30px; }}
                .email-item {{ margin-bottom: 20px; padding: 15px; border-left: 4px solid #ccc; background-color: #f9f9f9; }}
                .email-item.high {{ border-left-color: #ff4d4d; }}
                .email-item.medium {{ border-left-color: #ffad33; }}
                .email-item.low {{ border-left-color: #2ecc71; }}
                .email-sender {{ font-weight: bold; }}
                .email-subject {{ font-size: 16px; margin: 5px 0; }}
                .email-time {{ color: #888; font-size: 12px; }}
                .key-points {{ margin-top: 10px; }}
                .action-items {{ margin-top: 10px; color: #e74c3c; }}
                ul {{ padding-left: 20px; }}
                li {{ margin-bottom: 5px; }}
                .priority-tag {{ 
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                    color: white;
                }}
                .priority-high {{ background-color: #ff4d4d; }}
                .priority-medium {{ background-color: #ffad33; }}
                .priority-low {{ background-color: #2ecc71; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{period_name} Email Digest</h1>
                    <p>{today}</p>
                    <p>Total emails: {digest.email_count} | High priority: {digest.high_priority_count}</p>
                </div>
                <div class="summary">
        """
        
        # No emails section
        if not digest.summaries:
            html += "<p>No new emails during this period.</p>"
        
        # High priority emails section
        high_priority = [s for s in digest.summaries if s.priority == "High"]
        if high_priority:
            html += """
                <h2>⚠️ High Priority</h2>
            """
            for summary in high_priority:
                html += self._format_email_summary_html(summary)
        
        # Medium priority emails section
        medium_priority = [s for s in digest.summaries if s.priority == "Medium"]
        if medium_priority:
            html += """
                <h2>Medium Priority</h2>
            """
            for summary in medium_priority:
                html += self._format_email_summary_html(summary)
        
        # Low priority emails section
        low_priority = [s for s in digest.summaries if s.priority == "Low"]
        if low_priority:
            html += """
                <h2>Low Priority</h2>
            """
            for summary in low_priority:
                html += self._format_email_summary_html(summary)
        
        # Close HTML tags
        html += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_email_summary_html(self, summary: EmailSummary) -> str:
        """Format a single email summary as HTML"""
        priority_class = summary.priority.lower()
        time_str = summary.date.strftime("%I:%M %p")
        
        html = f"""
        <div class="email-item {priority_class}">
            <div class="email-sender">{summary.sender}</div>
            <div class="email-subject">{summary.subject}</div>
            <div class="email-time">{time_str}</div>
            <span class="priority-tag priority-{priority_class}">{summary.priority}</span>
            
            <div class="key-points">
                <strong>Key Points:</strong>
                <ul>
        """
        
        # Add key points
        for point in summary.key_points:
            html += f"<li>{point}</li>"
        
        html += """
                </ul>
            </div>
        """
        
        # Add action items if present
        if summary.action_items:
            html += """
            <div class="action-items">
                <strong>Action Items:</strong>
                <ul>
            """
            for action in summary.action_items:
                html += f"<li>{action}</li>"
            
            html += """
                </ul>
            </div>
            """
        
        html += "</div>"
        
        return html
    
    def send_email(self, digest: DigestReport) -> bool:
        """Send the digest email to recipients"""
        period_name = "Morning" if digest.period == "morning" else "Evening"
        today = digest.date.strftime("%B %d, %Y")
        
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"{period_name} Email Digest - {today}"
        msg['From'] = self.config.gmail_user
        msg['To'] = ", ".join(self.config.team_recipients)
        
        # Create HTML email body
        html_body = self.format_html_email(digest)
        msg.attach(MIMEText(html_body, 'html'))
        
        try:
            # Send email
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(self.config.gmail_user, self.config.gmail_app_password)
            server.sendmail(
                self.config.gmail_user, 
                self.config.team_recipients, 
                msg.as_string()
            )
            server.quit()
            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False
