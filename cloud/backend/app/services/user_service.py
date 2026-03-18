from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User


class UserService:
    """Service for managing multi-tenant users."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, clerk_user_id: str, email: str, display_name: str | None = None) -> User:
        """Get existing user or create a new one from Clerk data."""
        result = await self.session.execute(
            select(User).where(User.id == clerk_user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=clerk_user_id,
                email=email,
                display_name=display_name,
                plan="free",
                settings={},
                connector_credentials={},
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)

        return user

    async def get_user(self, clerk_user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == clerk_user_id)
        )
        return result.scalar_one_or_none()

    async def update_settings(self, clerk_user_id: str, settings: dict) -> User | None:
        user = await self.get_user(clerk_user_id)
        if user:
            user.settings = {**user.settings, **settings}
            await self.session.commit()
            await self.session.refresh(user)
        return user
