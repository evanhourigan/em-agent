from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....models.projects import Project
from ....schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate
from ...deps import get_db_session

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate, session: Session = Depends(get_db_session)
) -> ProjectOut:
    existing = session.execute(
        select(Project).where(Project.key == payload.key)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="project key already exists")
    project = Project(key=payload.key, name=payload.name)
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_db_session)) -> list[ProjectOut]:
    # Filter out soft-deleted projects
    rows = (
        session.execute(
            select(Project).where(Project.deleted_at.is_(None)).order_by(Project.id)
        )
        .scalars()
        .all()
    )
    return [ProjectOut.from_orm(p) for p in rows]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int, session: Session = Depends(get_db_session)
) -> ProjectOut:
    project = session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="not found")
    return ProjectOut.from_orm(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, payload: ProjectUpdate, session: Session = Depends(get_db_session)
) -> ProjectOut:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="not found")
    if payload.key is not None:
        # ensure uniqueness
        exists = session.execute(
            select(Project).where(Project.key == payload.key, Project.id != project_id)
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="project key already exists")
        project.key = payload.key
    if payload.name is not None:
        project.name = payload.name
    session.commit()
    session.refresh(project)
    return ProjectOut.from_orm(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, session: Session = Depends(get_db_session)) -> None:
    project = session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="not found")
    # Use soft delete instead of hard delete
    project.soft_delete()
    session.commit()
    return None
