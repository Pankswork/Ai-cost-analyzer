from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.user import User
from app.models.pydantic_models import UserCreate, UserLogin, TokenResponse, UserResponse
from app.services.auth_service import hash_password, verify_password, create_token
from app.middleware.auth_middleware import get_current_user

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    admin_emails = [e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()]
    is_admin = body.email.strip().lower() in admin_emails
    user = User(
        email=body.email, password_hash=hash_password(body.password),
        name=body.name, is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_token(user.id, user.is_admin)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    admin_emails = [e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()]
    if not user.is_admin and body.email.strip().lower() in admin_emails:
        user.is_admin = True
        await db.commit()
    token = create_token(user.id, user.is_admin)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
