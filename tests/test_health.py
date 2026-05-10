import asyncio

import api.routes.health as health_module


class DummySession:
    async def execute(self, *args, **kwargs):
        class R:
            pass

        return R()


class DummyRedis:
    async def ping(self):
        return True


def test_health_endpoint_overridden_dependencies():
    async def _run():
        body = await health_module.health_check(session=DummySession(), redis=DummyRedis())
        assert body["api"] == "ok"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"

    asyncio.run(_run())
