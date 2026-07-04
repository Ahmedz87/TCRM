"""Autochartist opportunities — native cards feed for the portal + dashboard."""
from fastapi import APIRouter, Query
import autochartist_api as AC

router = APIRouter(prefix="/autochartist", tags=["Autochartist"])


@router.get("/status")
def status():
    return {"mode": "mock" if AC.is_mock() else "live", "connected": not AC.is_mock()}


@router.get("/opportunities")
def opportunities(symbol: str = Query(""), limit: int = Query(12)):
    return {
        "mode": "mock" if AC.is_mock() else "live",
        "opportunities": AC.fetch_opportunities(symbol=symbol or None, limit=max(1, min(limit, 50))),
    }
