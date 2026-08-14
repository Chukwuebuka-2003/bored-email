import json
import logging
import re
from typing import List

from openai import OpenAI

from models import EmailMessage, EmailSummary, Config

logger = logging.getLogger(__name__)


class EmailSummarizer:
    """Summarizes emails via any OpenAI-compatible API (local or remote)."""

    def __init__(self, config: Config):
        self.config = config
        self.model = config.openai_model

        # OpenAI-compatible client. Works with LM Studio, llama.cpp, Ollama
        # (via its /v1 shim), vLLM, or the real OpenAI API — just point
        # `base_url` (and optionally `api_key`) at your server.
        self.client = OpenAI(
            api_key=config.openai_api_key or "not-needed",
            base_url=config.openai_base_url or None,
            timeout=config.llm_timeout,
            max_retries=2,
        )

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Parse JSON out of a model response that may include prose or fences."""
        if not text:
            return {}

        candidates = [text]

        # Strip markdown code fences if present.
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            candidates.insert(0, fenced.group(1))

        # Try to parse the largest balanced JSON object in the response.
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return {}

    @staticmethod
    def _normalize_priority(value) -> str:
        """Coerce free-form priority strings into High/Medium/Low."""
        if not isinstance(value, str):
            return "Low"
        v = value.strip().lower()
        if v in ("high", "urgent", "critical", "important"):
            return "High"
        if v in ("medium", "normal", "moderate"):
            return "Medium"
        return "Low"

    def summarize_email(self, email: EmailMessage) -> EmailSummary:
        """Summarize a single email."""

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

        Respond ONLY with a valid JSON object using this exact structure:
        {{
            "key_points": ["point 1", "point 2", ...],
            "action_items": ["action 1", "action 2", ...],
            "priority": "High|Medium|Low"
        }}
        """

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.config.llm_temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an assistant that summarizes emails into key points "
                        "and action items. Extract only the most important information "
                        "and be concise. Always answer with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        summary_content = response.choices[0].message.content or ""
        summary_data = self._extract_json(summary_content)

        if not summary_data:
            logger.warning(
                "Could not parse JSON from model for email %s; using fallback",
                email.message_id,
            )
            summary_data = {
                "key_points": ["Failed to parse email content"],
                "action_items": [],
                "priority": "Low",
            }

        key_points = summary_data.get("key_points", []) or []
        action_items = summary_data.get("action_items", []) or []

        # Tolerate models that return a single string instead of a list.
        if isinstance(key_points, str):
            key_points = [key_points]
        if isinstance(action_items, str):
            action_items = [action_items]

        return EmailSummary(
            message_id=email.message_id,
            sender=email.sender,
            subject=email.subject,
            key_points=key_points,
            action_items=action_items,
            priority=self._normalize_priority(summary_data.get("priority")),
            date=email.date,
        )

    def summarize_emails(self, emails: List[EmailMessage]) -> List[EmailSummary]:
        """Summarize a list of emails."""
        summaries = []
        for email in emails:
            try:
                summary = self.summarize_email(email)
                summaries.append(summary)
            except Exception as e:
                logger.error("Error summarizing email %s: %s", email.message_id, str(e))
                # Continue with other emails if one fails
                continue

        # Sort summaries by priority (High > Medium > Low)
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        summaries.sort(key=lambda x: (priority_order.get(x.priority, 3), x.date), reverse=True)

        return summaries
