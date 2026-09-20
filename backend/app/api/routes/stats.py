from fastapi import APIRouter
from app.services.stats_service import stats_service

router = APIRouter(prefix='/stats', tags=['stats'])


@router.get('')
def overview():
    return stats_service.overview()
