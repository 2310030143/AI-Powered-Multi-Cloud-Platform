from fastapi import APIRouter

router = APIRouter()


@router.post("/connect")
def connect_aws():
    return {"message": "AWS S3 connection — coming in Phase 2"}
