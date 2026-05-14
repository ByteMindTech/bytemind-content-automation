"""Email notification service — OVH SMTP for approval workflow."""

from __future__ import annotations

import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jose import jwt

from app.config import get_settings
from app.models import Article, ArticleRevision
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class EmailService:
    """Sends approval/rejection notification emails via OVH SMTP."""

    def _create_approval_token(self, article_id: uuid.UUID, action: str) -> str:
        """Create a signed JWT token for approve/reject links."""
        payload = {
            "article_id": str(article_id),
            "action": action,
            "exp": datetime.now(tz=timezone.utc)
            + timedelta(hours=_settings.approval_token_expiry_hours),
            "iat": datetime.now(tz=timezone.utc),
        }
        return jwt.encode(payload, _settings.jwt_secret_key, algorithm=_settings.jwt_algorithm)

    def _build_approval_email(
        self,
        article: Article,
        revision: ArticleRevision,
    ) -> tuple[str, str]:
        """Build HTML email content with approve/reject buttons."""
        approve_token = self._create_approval_token(article.id, "approve")
        reject_token = self._create_approval_token(article.id, "reject")

        base_url = _settings.approval_base_url.rstrip("/")
        approve_url = f"{base_url}/approval/approve/{approve_token}"
        reject_url = f"{base_url}/approval/reject/{reject_token}"

        # Format issues
        issues_html = ""
        if revision.issues:
            issues_list = revision.issues if isinstance(revision.issues, list) else []
            if issues_list:
                issues_html = "<h3>⚠️ Issues Found</h3><ul>"
                for issue in issues_list:
                    severity = issue.get("severity", "low")
                    color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#3498db"}.get(
                        severity, "#666"
                    )
                    issues_html += (
                        f'<li><span style="color:{color};font-weight:bold">[{severity.upper()}]</span> '
                        f'{issue.get("field", "")}: {issue.get("description", "")}</li>'
                    )
                issues_html += "</ul>"

        subject = f"[ByteMind] Article Review: {article.title} (Score: {revision.quality_score}/10)"

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f8f9fa;">
    <div style="background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <h1 style="color: #1a1a2e; margin-bottom: 8px;">📝 Article Ready for Review</h1>
        <p style="color: #666; font-size: 14px; margin-top: 0;">ByteMind Content Automation</p>
        
        <hr style="border: 1px solid #eee; margin: 24px 0;">
        
        <h2 style="color: #333;">{article.title}</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding: 8px 0; color: #666;">Category</td><td style="padding: 8px 0; font-weight: bold;">{article.category}</td></tr>
            <tr><td style="padding: 8px 0; color: #666;">Tags</td><td style="padding: 8px 0;">{', '.join(article.tags or [])}</td></tr>
            <tr><td style="padding: 8px 0; color: #666;">Quality Score</td><td style="padding: 8px 0; font-size: 24px; font-weight: bold; color: {'#27ae60' if revision.quality_score >= 7 else '#f39c12' if revision.quality_score >= 5 else '#e74c3c'};">{revision.quality_score}/10</td></tr>
            <tr><td style="padding: 8px 0; color: #666;">AI Provider</td><td style="padding: 8px 0;">{revision.provider} ({revision.model})</td></tr>
        </table>
        
        <h3>📋 Summary</h3>
        <p style="color: #444; line-height: 1.6;">{revision.summary}</p>
        
        {issues_html}
        
        <hr style="border: 1px solid #eee; margin: 24px 0;">
        
        <div style="text-align: center; margin: 32px 0;">
            <a href="{approve_url}" style="display: inline-block; padding: 14px 32px; background: #27ae60; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 0 8px;">✅ Approve & Publish</a>
            <a href="{reject_url}" style="display: inline-block; padding: 14px 32px; background: #e74c3c; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 0 8px;">❌ Reject</a>
        </div>
        
        <p style="color: #999; font-size: 12px; text-align: center;">
            Links expire in {_settings.approval_token_expiry_hours} hours. 
            Auto-approve threshold: score ≥ {_settings.auto_approve_threshold}/10.
        </p>
    </div>
</body>
</html>"""
        return subject, html

    async def send_approval_email(
        self,
        article: Article,
        revision: ArticleRevision,
    ) -> bool:
        """Send approval notification email. Returns True on success."""
        if not _settings.smtp_user or not _settings.approval_email:
            logger.warning("email_not_configured", reason="SMTP_USER or APPROVAL_EMAIL not set")
            return False

        subject, html_body = self._build_approval_email(article, revision)

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{_settings.smtp_from_name} <{_settings.smtp_user}>"
        msg["To"] = _settings.approval_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(_settings.smtp_host, _settings.smtp_port, context=context) as server:
                server.login(_settings.smtp_user, _settings.smtp_password)
                server.send_message(msg)

            logger.info(
                "approval_email_sent",
                to=_settings.approval_email,
                article_title=article.title,
                quality_score=revision.quality_score,
            )
            return True

        except Exception as exc:
            logger.error(
                "approval_email_failed",
                error=str(exc),
                article_id=str(article.id),
            )
            return False

    @staticmethod
    def decode_approval_token(token: str) -> dict | None:
        """Decode and validate an approval token. Returns payload or None if invalid/expired."""
        try:
            payload = jwt.decode(
                token,
                _settings.jwt_secret_key,
                algorithms=[_settings.jwt_algorithm],
            )
            return payload
        except Exception as exc:
            logger.warning("approval_token_invalid", error=str(exc))
            return None
