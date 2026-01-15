"""
Authentication API routes.
Note: These are implemented but not enforced on other endpoints yet.
"""
from fastapi import APIRouter, HTTPException
from app.auth import (
    create_access_token,
    hash_password,
    verify_password,
    get_user,
    create_user,
    UserCreate,
    UserLogin,
    Token
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=Token)
async def register(user_data: UserCreate):
    """
    Register a new user.
    Returns JWT token upon successful registration.
    """
    # Check if user exists
    existing_user = get_user(user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Hash password and create user
    hashed_password = hash_password(user_data.password)
    create_user(user_data.username, hashed_password)
    
    # Create access token
    access_token = create_access_token(data={"sub": user_data.username})
    
    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """
    Login endpoint.
    Returns JWT token upon successful authentication.
    """
    # Get user
    user = get_user(user_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create access token
    access_token = create_access_token(data={"sub": user_data.username})
    
    return Token(access_token=access_token)


@router.get("/me")
async def get_current_user_info():
    """
    Get current user information.
    Note: This endpoint is not yet protected - will be in future update.
    """
    return {"message": "User authentication system is implemented but not enforced yet"}
