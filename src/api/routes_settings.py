from fastapi import APIRouter

from src.api.deps import app_state
from src.api.schemas import CollectorStatusResponse, StorageInfoResponse
from src.collector import collector_status, start_collector, stop_collector

router = APIRouter(prefix="/api/collector")


@router.get("/status")
def get_collector_status() -> CollectorStatusResponse:
    return CollectorStatusResponse(
        running=collector_status(),
        interval=app_state.collector_interval,
    )


@router.post("/start")
def start(interval: int = 60) -> CollectorStatusResponse:
    app_state.collector_interval = interval
    if not collector_status():
        start_collector(interval)
    return CollectorStatusResponse(
        running=collector_status(),
        interval=interval,
    )


@router.post("/stop")
def stop() -> CollectorStatusResponse:
    if collector_status():
        stop_collector()
    return CollectorStatusResponse(
        running=collector_status(),
        interval=app_state.collector_interval,
    )


@router.get("/storage")
def get_storage_info() -> StorageInfoResponse:
    ns = app_state.nav_store
    if ns is None:
        return StorageInfoResponse(size_bytes=0, nav_snapshots=0, position_snapshots=0)
    info = ns.storage_info()
    return StorageInfoResponse(**info)


@router.delete("/storage")
def clear_storage() -> StorageInfoResponse:
    ns = app_state.nav_store
    if ns is None:
        return StorageInfoResponse(size_bytes=0, nav_snapshots=0, position_snapshots=0)
    ns.clear_all()
    info = ns.storage_info()
    return StorageInfoResponse(**info)
