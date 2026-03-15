from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.runtime_settings import EDITABLE_KEYS, get_all, save_override

router = APIRouter()


class SettingUpdate(BaseModel):
    key: str
    value: float | int | str


@router.get("/settings")
async def get_settings() -> dict:
    return get_all()


@router.put("/settings")
async def update_setting(body: SettingUpdate) -> dict:
    if body.key not in EDITABLE_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {body.key}")
    try:
        await save_override(body.key, body.value)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return get_all()
