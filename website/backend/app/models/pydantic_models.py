from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    is_admin: bool = False

    model_config = {"from_attributes": True}


class ToolResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    url: str
    free_tier: Optional[str] = None
    paid_tier: Optional[str] = None
    best_for: Optional[str] = None
    verdict: Optional[str] = None
    models: Optional[str] = None
    pros: Optional[str] = None
    cons: Optional[str] = None
    category_slug: Optional[str] = None
    category_title: Optional[str] = None
    category_icon: Optional[str] = None

    model_config = {"from_attributes": True}


class ToolListResponse(BaseModel):
    tools: list[ToolResponse]
    total: int
    page: int
    page_size: int


class CategoryResponse(BaseModel):
    id: int
    slug: str
    title: str
    description: Optional[str] = None
    icon: str = "🤖"
    tool_count: int = 0

    model_config = {"from_attributes": True}


class ToolSubmissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=500)
    category_slug: Optional[str] = None
    description: Optional[str] = None
    submitter_email: Optional[EmailStr] = None


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    tool_id: int
    rating: int
    body: Optional[str] = None
    user_email: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    message: str = Field(min_length=1)


class NewsletterSubscribe(BaseModel):
    email: EmailStr


class FavoriteResponse(BaseModel):
    tool_id: int
    tool_name: Optional[str] = None
    tool_slug: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class CostReportResponse(BaseModel):
    id: int
    report_uuid: str
    total_resources: int
    total_recommendations: int
    total_estimated_savings: float
    status: str
    triggered_by: str
    created_at: str
    completed_at: Optional[str] = None

    model_config = {"from_attributes": True}


class CostReportDetailResponse(CostReportResponse):
    resources: Optional[list] = None
    recommendations: Optional[list] = None
    aws_account_id: Optional[str] = None
    aws_region: Optional[str] = None


class AnalysisTriggerRequest(BaseModel):
    triggered_by: str = "manual"


class AnalysisRunResponse(BaseModel):
    report_uuid: str
    status: str
    message: str
