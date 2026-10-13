from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import uuid

from Database.controller import get_db
from Database.models.user import User
from services.auth import require_admin, hash_password, ENV_ADMIN_ID, ENV_USER_ID
from settings import settings

router = APIRouter()

class UserCreate(BaseModel):
    name: Optional[str] = None
    username: str
    password: str
    role: Optional[str] = "user"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None

@router.get("")
def list_users(session = Depends(get_db), admin: User = Depends(require_admin)):
    db_users = session.query(User).all()
    
    return [{
        "id": u.id,
        "name": u.name,
        "username": u.username,
        "role": u.role,
        "status": u.status,
        "auth_source": u.auth_source,
        "builtIn": u.auth_source == "env"
    } for u in db_users]

@router.post("")
def create_user(req: UserCreate, session = Depends(get_db), admin: User = Depends(require_admin)):
    from sqlalchemy.exc import IntegrityError
    
    if req.role == "admin":
        raise HTTPException(status_code=400, detail="Only one admin is allowed (defined in .env)")

    clean_username = req.username.strip().lower()
    if clean_username in [settings.AUTH_ADMIN_USERNAME.lower(), settings.AUTH_USER_USERNAME.lower()]:
        raise HTTPException(status_code=409, detail="Username conflicts with built-in env account")

    new_user = User(
        id=f"usr-{uuid.uuid4()}",
        name=req.name or req.username,
        username=req.username,
        password_hash=hash_password(req.password),
        role="user",
        status="Active",
        auth_source="db",
        department_id="dept-default"
    )
    session.add(new_user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username already exists")
    
    return {"id": new_user.id, "message": "User created successfully"}

@router.patch("/{user_id}")
def update_user(user_id: str, req: UserUpdate, session = Depends(get_db), admin: User = Depends(require_admin)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.auth_source == "env":
        raise HTTPException(status_code=400, detail="edit .env")
        
    if req.name is not None:
        user.name = req.name
    if req.status is not None:
        user.status = req.status
    if req.password is not None and req.password != "":
        user.password_hash = hash_password(req.password)
        
    session.commit()
    return {"message": "User updated successfully"}

@router.delete("/{user_id}")
def delete_user(user_id: str, session = Depends(get_db), admin: User = Depends(require_admin)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.auth_source == "env":
        raise HTTPException(status_code=400, detail="Cannot disable env users here")
        
    user.status = "Disabled"
    session.commit()
    return {"message": "User disabled successfully"}
