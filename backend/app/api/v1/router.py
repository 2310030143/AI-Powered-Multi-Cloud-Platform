from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, health, cloud_google, cloud_s3, files, ai, documents, reports
)

api_router = APIRouter()

api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(cloud_google.router, prefix="/cloud/google", tags=["cloud-google"])
api_router.include_router(cloud_s3.router, prefix="/cloud/s3", tags=["cloud-s3"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(ai.router, tags=["ai"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
