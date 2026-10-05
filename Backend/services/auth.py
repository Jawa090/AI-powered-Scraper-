from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import hmac
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

from Database.controller import get_db
from Database.models.user import User
from Database.models.job import Job

from settings import settings

bearer = HTTPBearer()

ENV_ADMIN_ID = "usr-env-admin"
ENV_USER_ID = "usr-env-user"
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000)
    return f"pbkdf2_sha256$200000${salt}${hash_bytes.hex()}"

def verify_password(password: str, stored: str) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    parts = stored.split('$')
    if len(parts) != 4:
        return False
    _, iterations_str, salt, hash_hex = parts
    try:
        iterations = int(iterations_str)
        hash_bytes = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
        return hmac.compare_digest(hash_bytes.hex(), hash_hex)
    except Exception:
        return False

def authenticate(session, username: str, password: str) -> User | None:
    # 1) env admin 
    if username.lower() == settings.AUTH_ADMIN_USERNAME.lower():
        if hmac.compare_digest(password, settings.AUTH_ADMIN_PASSWORD):
            return session.query(User).filter(User.id == ENV_ADMIN_ID).first()
        return None
    
    # 2) env user
    if username.lower() == settings.AUTH_USER_USERNAME.lower():
        if hmac.compare_digest(password, settings.AUTH_USER_PASSWORD):
            return session.query(User).filter(User.id == ENV_USER_ID).first()
        return None
    
    # 3) DB users
    user = session.query(User).filter(
        User.username.ilike(username),
        User.auth_source == 'db',
        User.status == 'Active'
    ).first()
    
    if user and verify_password(password, user.password_hash):
        return user
    return None

def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(days=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), session = Depends(get_db)) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth credentials")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    user = session.get(User, user_id)
    if not user or user.status != "Active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
            
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

def enforce_scrape_limit(session, user_id: str) -> None:
    limit = settings.SCRAPES_PER_HOUR
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    
    count = session.query(Job).filter(
        Job.created_by == user_id,
        Job.created_at >= one_hour_ago
    ).count()
    
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
            detail=f"Rate limit exceeded: max {limit} scrapes per hour."
        )

def sync_env_users(session) -> None:
    for user_id, role, username in [
        (ENV_ADMIN_ID, "admin", settings.AUTH_ADMIN_USERNAME),
        (ENV_USER_ID, "user", settings.AUTH_USER_USERNAME)
    ]:
        user = session.get(User, user_id)
        if not user:
            user = User(id=user_id)
            session.add(user)
        user.username = username
        user.name = username
        user.email = None
        user.role = role
        user.department_id = "dept-default"
        user.auth_source = "env"
        user.password_hash = None
        user.status = "Active"
        user.role_title = "Built-in account"
