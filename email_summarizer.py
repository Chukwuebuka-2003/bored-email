from typing import List
import openai
import json
from models import EmailMessage, EmailSummary, Config

class EmailSummarizer:
    """Uses OpenAI to summarize emails"""
    
    def __init__(self, config: Config):
        self.config = config
        openai.api_key = config.openai_api_key
        self.model = config.openai_model
    
    def summarize_email(self, email: EmailMessage) -> EmailSummary:
        """Summarize a single email using OpenAI"""
        
        # Construct the prompt for the OpenAI API
        prompt = f"""
        Please summarize the following email and extract key information.
        
        FROM: {email.sender}
        SUBJECT: {email.subject}
        DATE: {email.date}
        BODY:
        {email.body}
        
        Please provide:
        1. A list of 2-5 key points from this email
        2. Any action items that need to be addressed
        3. A priority level (High/Medium/Low) based on urgency and importance
        
        Format your response as JSON with the following structure:
        {{
            "key_points": ["point 1", "point 2", ...],
            "action_items": ["action 1", "action 2", ...],
            "priority": "High|Medium|Low"
        }}
        """
        
        # Call the OpenAI API
        response = openai.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an assistant that summarizes emails into key points and action items. Extract only the most important information and be concise."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parse the response - use standard JSON parsing
        summary_content = response.choices[0].message.content
        try:
            summary_data = json.loads(summary_content)
        except json.JSONDecodeError:
            # Fallback parsing if not valid JSON
            summary_data = {
                "key_points": ["Failed to parse email content"],
                "action_items": [],
                "priority": "Low"
            }
        
        # Create and return the EmailSummary object
        return EmailSummary(
            message_id=email.message_id,
            sender=email.sender,
            subject=email.subject,
            key_points=summary_data.get("key_points", []),
            action_items=summary_data.get("action_items", []),
            priority=summary_data.get("priority", "Low"),
            date=email.date
        )
    
    def summarize_emails(self, emails: List[EmailMessage]) -> List[EmailSummary]:
        """Summarize a list of emails"""
        summaries = []
        for email in emails:
            try:
                summary = self.summarize_email(email)
                summaries.append(summary)
            except Exception as e:
                print(f"Error summarizing email {email.message_id}: {str(e)}")
                # Continue with other emails if one fails
                continue
        
        # Sort summaries by priority (High > Medium > Low)
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        summaries.sort(key=lambda x: (priority_order.get(x.priority, 3), x.date), reverse=True)
        
        return summaries
