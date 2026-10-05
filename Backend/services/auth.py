from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os
from datetime import datetime, timezone, timedelta

from Database.controller import db
from Database.models.user import User
from Database.models.job import Job

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth credentials")
    except jwt.DecodeError:
        # Fallback for dev: assume the token IS the user_id if it's not a valid JWT
        user_id = token
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
        
    session = db.get_session()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        # Auto-create dev user if it's a known placeholder
        if user_id in ["usr-ahmed", "ahmed"] and os.getenv("ENV") != "production":
            user = User(
                id=user_id, 
                email=f"{user_id}@example.com", 
                name="Ahmed Khan", 
                role="admin", 
                department_id="dept-sales-1"
            )
            session.add(user)
            try:
                session.commit()
            except Exception:
                session.rollback()
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

def enforce_scrape_limit(current_user: User = Depends(get_current_user)) -> None:
    limit = int(os.getenv("SCRAPES_PER_HOUR", "10"))
    session = db.get_session()
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    
    count = session.query(Job).filter(
        Job.created_by == current_user.id,
        Job.created_at >= one_hour_ago
    ).count()
    
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail=f"Rate limit exceeded: max {limit} scrapes per hour."
        )
