import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, selectinload

from backend.app.core.dependencies import CurrentUser, get_db
from shared.database.models.content import Movie
from backend.app.modules.content.movies.schemas import MovieDetailRead, MovieRead
from shared.schemas.common import paginated, success

router = APIRouter(prefix="/api/content/movies", tags=["content-movies"])

ALLOWED_SORT_FIELDS = {
    "created_at": Movie.created_at,
    "updated_at": Movie.updated_at,
    "code": Movie.code,
    "source_name": Movie.source_name,
    "release_date": Movie.release_date,
    "rating": Movie.rating,
}


@router.get("")
def list_movies(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None, max_length=200),
    source_task_name: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
) -> dict:
    query = db.query(Movie)

    if keyword:
        query = query.filter(
            or_(
                Movie.code.ilike(f"%{keyword}%"),
                Movie.source_name.ilike(f"%{keyword}%"),
                Movie.director.ilike(f"%{keyword}%"),
                Movie.maker.ilike(f"%{keyword}%"),
                Movie.series.ilike(f"%{keyword}%"),
            )
        )

    if source_task_name:
        # For SQLite tests, use Python filtering; for PostgreSQL use ARRAY contains
        try:
            query = query.filter(Movie.source_task_names.contains([source_task_name]))
        except Exception:
            # SQLite fallback - will be filtered in Python
            pass

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Movie.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    total = query.count()
    rows = query.offset(skip).limit(limit).all()

    # SQLite fallback for source_task_name filtering
    if source_task_name and db.bind.dialect.name == "sqlite":
        rows = [r for r in rows if source_task_name in (r.source_task_names or [])]
        total = len(rows)

    return paginated(
        rows=[MovieRead.model_validate(r).model_dump(mode="json") for r in rows],
        total=total,
    )


@router.get("/{movie_id}")
def get_movie(movie_id: uuid.UUID, _current_user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    movie = db.query(Movie).options(selectinload(Movie.magnets)).filter(Movie.id == movie_id).first()
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return success(data=MovieDetailRead.model_validate(movie).model_dump(mode="json"))
