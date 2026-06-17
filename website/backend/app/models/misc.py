from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, JSON, Float
from app.db.session import Base


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    replied = Column(Boolean, default=False)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    confirmed = Column(Boolean, default=False)
    subscribed = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AffiliateClick(Base):
    __tablename__ = "affiliate_clicks"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(Integer, nullable=True)
    url = Column(String(500), nullable=False)
    referrer = Column(String(500), nullable=True)
    user_agent = Column(String(500), nullable=True)
    clicked_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CostReport(Base):
    __tablename__ = "cost_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_uuid = Column(String(36), unique=True, index=True, nullable=False)
    aws_account_id = Column(String(12), nullable=True)
    aws_region = Column(String(20), nullable=True)
    total_resources = Column(Integer, default=0)
    total_recommendations = Column(Integer, default=0)
    total_estimated_savings = Column(Float, default=0.0)
    resources = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    status = Column(String(20), default="completed")
    triggered_by = Column(String(50), default="cronjob")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
