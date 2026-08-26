from fastapi import APIRouter

router = APIRouter()


@router.post("/generate")
def generate_report():
    return {"message": "Report generation — coming in Phase 6"}
