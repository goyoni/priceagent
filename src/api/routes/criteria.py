"""FastAPI routes for criteria management."""

import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel

from src.db.criteria_store import get_criteria_store
from src.config.settings import settings

router = APIRouter(prefix="/api/criteria", tags=["criteria"])


def verify_dashboard_auth(
    auth_token: Optional[str] = Query(None, alias="auth"),
    x_dashboard_auth: Optional[str] = Header(None),
) -> bool:
    """Verify dashboard authentication.

    In development (no password set), always allows access.
    In production (password set), requires valid auth token.
    """
    # No password configured = development mode, allow all
    if not settings.dashboard_password:
        return True

    # Check query param or header
    token = auth_token or x_dashboard_auth
    if not token:
        raise HTTPException(status_code=401, detail="Dashboard authentication required")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, settings.dashboard_password):
        raise HTTPException(status_code=401, detail="Invalid dashboard credentials")

    return True


class CriterionModel(BaseModel):
    """A single criterion for a product category."""
    name: str
    description: str
    unit: Optional[str] = None
    options: Optional[List[str]] = None


class CategoryCriteriaModel(BaseModel):
    """Criteria for a product category."""
    category: str
    criteria: List[CriterionModel]


class UpdateCriteriaRequest(BaseModel):
    """Request to update criteria for a category."""
    criteria: List[CriterionModel]


@router.get("/")
async def list_categories(_auth: bool = Depends(verify_dashboard_auth)):
    """List all known product categories with their criteria."""
    store = get_criteria_store()
    categories = await store.list_categories()

    # Fetch criteria count for each category
    result = []
    for cat in categories:
        criteria = await store.get_criteria(cat["category"])
        result.append({
            **cat,
            "criteria_count": len(criteria) if criteria else 0,
        })

    return {"categories": result}


@router.get("/{category}")
async def get_category_criteria(
    category: str,
    _auth: bool = Depends(verify_dashboard_auth),
):
    """Get criteria for a specific category."""
    store = get_criteria_store()
    criteria = await store.get_criteria(category)

    if criteria is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Category '{category}' not found"}
        )

    # Get metadata
    categories = await store.list_categories()
    cat_info = next((c for c in categories if c["category"] == category.lower()), None)

    return {
        "category": category.lower(),
        "criteria": criteria,
        "source": cat_info["source"] if cat_info else "unknown",
        "created_at": cat_info["created_at"] if cat_info else None,
        "updated_at": cat_info["updated_at"] if cat_info else None,
    }


@router.put("/{category}")
async def update_category_criteria(
    category: str,
    request: UpdateCriteriaRequest,
    _auth: bool = Depends(verify_dashboard_auth),
):
    """Update criteria for a category."""
    store = get_criteria_store()

    # Convert Pydantic models to dicts
    criteria_dicts = [c.model_dump(exclude_none=True) for c in request.criteria]

    await store.save_criteria(category, criteria_dicts, source="manual")

    return {
        "status": "updated",
        "category": category.lower(),
        "criteria_count": len(criteria_dicts),
    }


@router.post("/{category}")
async def create_category(
    category: str,
    request: UpdateCriteriaRequest,
    _auth: bool = Depends(verify_dashboard_auth),
):
    """Create a new category with criteria."""
    store = get_criteria_store()

    # Check if already exists
    existing = await store.get_criteria(category)
    if existing:
        return JSONResponse(
            status_code=409,
            content={"error": f"Category '{category}' already exists. Use PUT to update."}
        )

    # Convert Pydantic models to dicts
    criteria_dicts = [c.model_dump(exclude_none=True) for c in request.criteria]

    await store.save_criteria(category, criteria_dicts, source="manual")

    return {
        "status": "created",
        "category": category.lower(),
        "criteria_count": len(criteria_dicts),
    }


@router.delete("/{category}")
async def delete_category(
    category: str,
    _auth: bool = Depends(verify_dashboard_auth),
):
    """Delete a category and its criteria."""
    store = get_criteria_store()
    success = await store.delete_category(category)

    if not success:
        return JSONResponse(
            status_code=404,
            content={"error": f"Category '{category}' not found"}
        )

    return {"status": "deleted", "category": category.lower()}
