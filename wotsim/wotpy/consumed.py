import wotpy.wot.consumed.thing


class ConsumedThing(wotpy.wot.consumed.thing.ConsumedThing):
    async def invoke_action(self, *args, **kwargs):
        return await super().invoke_action(*args, **kwargs)

    async def write_property(self, *args, **kwargs):
        return await super().write_property(*args, **kwargs)

    async def read_property(self, *args, **kwargs):
        return await super().read_property(*args, **kwargs)
