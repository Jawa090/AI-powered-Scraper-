import pytest
from Database.controller import session_scope, get_db

def test_two_scopes_give_different_sessions():
    with session_scope() as s1:
        with session_scope() as s2:
            assert s1 is not s2

def test_objects_stay_readable_after_commit():
    from Database.models.user import User
    
    import uuid
    uid = f"usr-test-{uuid.uuid4().hex[:6]}"
    test_email = f"test_{uid}@example.com"
    with session_scope() as s:
        # Check that we can create a user and read it after commit (because expire_on_commit=False)
        u = User(id=uid, email=test_email, name="Test User")
        s.add(u)
        s.commit()
        # Should be readable without Error
        assert u.email == test_email
        s.delete(u)
        s.commit()
