import os
import sys
import uuid
import getpass
from sqlalchemy import text

# Add Backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../Backend')))

from Database.controller import session_scope
from Database.models.user import User
from services.auth import hash_password
from sqlalchemy.exc import IntegrityError

def main():
    print("=== Create DataOps User ===")
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    name = input("Name (optional, defaults to username): ").strip()
    if not name:
        name = username
        
    password = getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty.")
        return
        
    confirm = getpass.getpass("Confirm Password: ")
    if password != confirm:
        print("Passwords do not match.")
        return
        
    with session_scope() as session:
        new_user = User(
            id=f"usr-{uuid.uuid4()}",
            name=name,
            username=username,
            password_hash=hash_password(password),
            role="user",
            status="Active",
            auth_source="db",
            department_id="dept-default"
        )
        session.add(new_user)
        try:
            session.commit()
            print(f"\nUser '{username}' created successfully!")
        except IntegrityError:
            session.rollback()
            print(f"\nError: A user with username '{username}' already exists.")

if __name__ == "__main__":
    main()
