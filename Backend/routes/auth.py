from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from Database.controller import get_db
from services.auth import authenticate, create_access_token, get_current_user
from Database.models.user import User

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginRequest, session = Depends(get_db)):
    user = authenticate(session, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_access_token(user)
    
    return {
        "accessToken": token,
        "tokenType": "bearer",
        "expiresIn": 86400,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "departmentId": user.department_id,
            "departmentName": user.department.name if getattr(user, "department", None) else None,
        }
    }

@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "departmentId": user.department_id,
        "departmentName": user.department.name if getattr(user, "department", None) else None,
    }
