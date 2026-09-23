"""Public branding endpoint — no authentication required.

Returns the current branding settings so the frontend can render the login
screen and favicon/title before the user has a session.

Hosted-only: registered in main.py only when MODE != 'local'.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/v1", tags=["branding"])


class BrandingOut(BaseModel):
    org_name: str | None
    logo: str | None


@router.get("/branding", response_model=BrandingOut)
async def get_branding(request: Request) -> BrandingOut:
    """Return the active branding (org_name + logo data-URI).

    No authentication required — used by the login page and SSR metadata
    before the user has a session.  If the row is missing for any reason,
    returns null for both fields (frontend falls back to defaults).
    """
    pool = request.app.state.pool
    row = await pool.fetchrow(
        "SELECT org_name, logo_data_uri FROM branding_settings WHERE id = true"
    )
    if row is None:
        return BrandingOut(org_name=None, logo=None)
    return BrandingOut(org_name=row["org_name"], logo=row["logo_data_uri"])
