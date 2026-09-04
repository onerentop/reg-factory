from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.base_repository import BaseRepository
from gateway.models import User


class UserRepository(BaseRepository[User]):
    model_class = User

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


