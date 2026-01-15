"""
User models for authentication.
Note: This is a simple in-memory user store for demonstration.
In production, use a database.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict


class User(BaseModel):
    """User model"""
    username: str
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class UserInDB(User):
    """User as stored in database"""
    pass


class UserCreate(BaseModel):
    """User creation request"""
    username: str
    password: str


class UserLogin(BaseModel):
    """User login request"""
    username: str
    password: str


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data"""
    username: Optional[str] = None


# Simple in-memory user store (replace with database in production)
fake_users_db: Dict[str, UserInDB] = {}


def get_user(username: str) -> Optional[UserInDB]:
    """Get user from store"""
    return fake_users_db.get(username)


def create_user(username: str, hashed_password: str) -> UserInDB:
    """Create a new user"""
    user = UserInDB(
        username=username,
        hashed_password=hashed_password,
        created_at=datetime.utcnow()
    )
    fake_users_db[username] = user
    return user
