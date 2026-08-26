from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_files():
    return {"message": "File listing — coming in Phase 2"}


@router.get("/{file_id}")
def get_file(file_id: str):
    return {"message": f"File {file_id} — coming in Phase 2"}


@router.post("/{file_id}/process")
def process_file(file_id: str):
    return {"message": f"Processing {file_id} — coming in Phase 3"}
