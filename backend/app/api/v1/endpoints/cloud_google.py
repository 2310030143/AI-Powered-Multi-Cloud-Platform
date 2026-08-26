from fastapi import APIRouter

router = APIRouter()


@router.post("/connect")
def connect_google():
    return {"message": "Google Drive connection — coming in Phase 2"}


@router.get("/callback")
def google_callback():
    return {"message": "Google OAuth callback — coming in Phase 2"}
