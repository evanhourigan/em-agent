from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....models.identities import Identity
from ....schemas.identities import IdentityCreate, IdentityOut
from ...deps import get_db_session

router = APIRouter(prefix="/v1/identities", tags=["identities"])


@router.get("", response_model=list[IdentityOut])
def list_identities(session: Session = Depends(get_db_session)) -> list[IdentityOut]:
    rows = session.execute(select(Identity).order_by(Identity.id)).scalars().all()
    return [IdentityOut.from_orm(x) for x in rows]


@router.post("", response_model=IdentityOut, status_code=201)
def create_identity(
    payload: IdentityCreate, session: Session = Depends(get_db_session)
) -> IdentityOut:
    ident = Identity(
        external_type=payload.external_type,
        external_id=payload.external_id,
        user_id=payload.user_id,
        display_name=payload.display_name,
        meta=payload.meta,
    )
    session.add(ident)
    session.commit()
    session.refresh(ident)
    return IdentityOut.from_orm(ident)
