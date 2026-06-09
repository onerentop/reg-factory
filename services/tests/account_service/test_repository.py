import pytest
import uuid
from shared.database import DatabaseManager
from shared.base_model import BaseModel
from account_service.models import Account, RegistrationStep, AccountPlatform, AccountStatus, StepStatus
from account_service.repository import AccountRepository, StepRepository


@pytest.fixture
async def db():
    manager = DatabaseManager(url="sqlite+aiosqlite:///")
    async with manager.engine.begin() as conn:
        await conn.run_sync(Account.__table__.create, checkfirst=True)
        await conn.run_sync(RegistrationStep.__table__.create, checkfirst=True)
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_create_account(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        account = await repo.create(
            email="test@outlook.com",
            platform=AccountPlatform.OUTLOOK,
            status=AccountStatus.PENDING,
            total_steps=5,
        )
        assert account.id is not None
        assert account.email == "test@outlook.com"
        assert account.platform == AccountPlatform.OUTLOOK


@pytest.mark.asyncio
async def test_create_steps(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        account = await repo.create(
            email="steps@test.com",
            platform=AccountPlatform.GOOGLE,
            status=AccountStatus.PENDING,
            total_steps=3,
        )
        step_repo = StepRepository(session)
        steps = await step_repo.create_steps(
            account.id, ["Fill name", "Set password", "Phone verify"]
        )
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[2].name == "Phone verify"


@pytest.mark.asyncio
async def test_get_with_steps(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        account = await repo.create(
            email="full@test.com",
            platform=AccountPlatform.OUTLOOK,
            status=AccountStatus.SUCCESS,
            total_steps=2,
        )
        step_repo = StepRepository(session)
        await step_repo.create_steps(account.id, ["Step A", "Step B"])

    async with db.get_session() as session:
        repo = AccountRepository(session)
        found = await repo.get_with_steps(account.id)
        assert found is not None
        assert len(found.steps) == 2


@pytest.mark.asyncio
async def test_list_filtered_by_platform(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        await repo.create(email="a@outlook.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.SUCCESS, total_steps=0)
        await repo.create(email="b@gmail.com", platform=AccountPlatform.GOOGLE, status=AccountStatus.SUCCESS, total_steps=0)
        await repo.create(email="c@outlook.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.FAILED, total_steps=0)

    async with db.get_session() as session:
        repo = AccountRepository(session)
        items, total = await repo.list_filtered(platform="outlook")
        assert total == 2
        assert all(a.platform == AccountPlatform.OUTLOOK for a in items)


@pytest.mark.asyncio
async def test_list_filtered_by_status(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        await repo.create(email="s1@test.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.SUCCESS, total_steps=0)
        await repo.create(email="s2@test.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.FAILED, total_steps=0)

    async with db.get_session() as session:
        repo = AccountRepository(session)
        items, total = await repo.list_filtered(status="failed")
        assert total == 1
        assert items[0].status == AccountStatus.FAILED


@pytest.mark.asyncio
async def test_delete_batch(db):
    async with db.get_session() as session:
        repo = AccountRepository(session)
        a1 = await repo.create(email="d1@test.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.PENDING, total_steps=0)
        a2 = await repo.create(email="d2@test.com", platform=AccountPlatform.OUTLOOK, status=AccountStatus.PENDING, total_steps=0)
        ids = [a1.id, a2.id]

    async with db.get_session() as session:
        repo = AccountRepository(session)
        deleted = await repo.delete_batch(ids)
        assert deleted == 2
