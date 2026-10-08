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
    user = session.query(User).filter(
        User.username.ilike(username),
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
        "exp": now + timedelta(hours=8)
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

def sync_env_users(session) -> None:
    """Create or migrate built-ins once, preserving resets and disabled status."""
    for uid, role, username, password in [
        (ENV_ADMIN_ID, 'admin', settings.AUTH_ADMIN_USERNAME, settings.AUTH_ADMIN_PASSWORD),
        (ENV_USER_ID, 'user', settings.AUTH_USER_USERNAME, settings.AUTH_USER_PASSWORD),
    ]:
        user = session.get(User, uid)
        if not user:
            user = User(id=uid, username=username, name=username, role=role, status='Active',
                department_id='dept-default', role_title='Built-in account', auth_source='db')
            session.add(user)
        if not user.password_hash:
            user.password_hash = hash_password(password)
        user.auth_source = 'db'
        if role == 'user' and not user.email:
            user.email = settings.AUTH_USER_EMAIL or (username if '@' in username else None)
