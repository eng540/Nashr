import pytest
from app.application.manual_artifacts import create_manual_artifact
from app.application.generic_artifact_review import GenericArtifactReviewService
from app.application.publications import CreateTelegramDraft, ApproveAndPublish
from app.application.live_locations import create_operation, execute_operation, list_live_locations
from app.infrastructure.database.session import SessionFactory
from app.domain.publications import PublishResult


@pytest.mark.asyncio
async def test_live_location_update_stop_are_reviewed_one_attempt_and_same_message():
    class Publisher:
        calls=[]
        async def publish(self,**kwargs):return PublishResult('321')
        async def update_live_location(self,**kwargs):self.calls.append(kwargs)
    pub=Publisher()
    async with SessionFactory() as session:
        item=await create_manual_artifact(session,kind='TEXT',title='Synthetic live point',content='Synthetic0,0for60seconds',native={'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':60})
        await GenericArtifactReviewService(session).approve(item.id)
        draft=await CreateTelegramDraft.execute_for_artifact(session,item,'private-fixture')
        result=await ApproveAndPublish(pub).execute(session,draft.id)
        operation=await create_operation(session,result.id,action='UPDATE',latitude=.001,longitude=.001)
        assert operation['status']=='DRAFT' and not pub.calls
        assert (await create_operation(session,result.id,action='UPDATE',latitude=.001,longitude=.001))['id']==operation['id']
        from uuid import UUID
        completed=await execute_operation(session,UUID(operation['id']),pub)
        assert completed['status']=='COMPLETED'
        with pytest.raises(ValueError,match='DRAFT'):await execute_operation(session,UUID(operation['id']),pub)
        assert pub.calls[0]=={'destination':'private-fixture','message_id':'321','action':'UPDATE','payload':{'latitude':.001,'longitude':.001}}
        stop=await create_operation(session,result.id,action='STOP')
        assert (await execute_operation(session,UUID(stop['id']),pub))['status']=='COMPLETED'
        assert len(pub.calls)==2 and pub.calls[1]['message_id']=='321'
        assert not (await list_live_locations(session,item.id))[0]['active']
        with pytest.raises(ValueError,match='stopped'):await create_operation(session,result.id,action='UPDATE',latitude=0,longitude=0)


@pytest.mark.asyncio
async def test_ambiguous_location_operation_is_not_retryable():
    class Publisher:
        calls=0
        async def publish(self,**kwargs):return PublishResult('322')
        async def update_live_location(self,**kwargs):
            self.calls+=1
            raise TimeoutError('Uncertain response')
    pub=Publisher()
    async with SessionFactory() as session:
        item=await create_manual_artifact(session,kind='TEXT',title='Synthetic live point',content='Synthetic0,0for60seconds',native={'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':60})
        await GenericArtifactReviewService(session).approve(item.id)
        draft=await CreateTelegramDraft.execute_for_artifact(session,item,'private-fixture')
        result=await ApproveAndPublish(pub).execute(session,draft.id)
        operation=await create_operation(session,result.id,action='UPDATE',latitude=.001,longitude=.001)
        from uuid import UUID
        assert (await execute_operation(session,UUID(operation['id']),pub))['status']=='UNCERTAIN'
        with pytest.raises(ValueError,match='DRAFT'):await execute_operation(session,UUID(operation['id']),pub)
        with pytest.raises(ValueError,match='settle'):await create_operation(session,result.id,action='STOP')
        assert pub.calls==1


@pytest.mark.asyncio
async def test_unexecuted_location_operation_can_be_cancelled():
    from app.application.live_locations import cancel_operation
    from uuid import UUID
    class Publisher:
        async def publish(self,**kwargs):return PublishResult('323')
    async with SessionFactory() as session:
        item=await create_manual_artifact(session,kind='TEXT',title='Synthetic cancel point',content='Synthetic test',native={'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':60})
        await GenericArtifactReviewService(session).approve(item.id)
        draft=await CreateTelegramDraft.execute_for_artifact(session,item,'private-fixture')
        result=await ApproveAndPublish(Publisher()).execute(session,draft.id)
        operation=await create_operation(session,result.id,action='UPDATE',latitude=.001,longitude=.001)
        assert (await cancel_operation(session,UUID(operation['id'])))['status']=='CANCELLED'
        stop=await create_operation(session,result.id,action='STOP')
        assert stop['status']=='DRAFT'


@pytest.mark.asyncio
async def test_location_operation_has_one_concurrent_executor():
    import asyncio
    from uuid import UUID
    class Publisher:
        calls=0
        async def publish(self,**kwargs):return PublishResult('324')
        async def update_live_location(self,**kwargs):
            self.calls+=1
            await asyncio.sleep(.05)
    pub=Publisher()
    async with SessionFactory() as session:
        item=await create_manual_artifact(session,kind='TEXT',title='Concurrent point',content='Synthetic test',native={'type':'LIVE_LOCATION','latitude':0,'longitude':0,'live_period':60})
        await GenericArtifactReviewService(session).approve(item.id)
        draft=await CreateTelegramDraft.execute_for_artifact(session,item,'private-fixture')
        result=await ApproveAndPublish(pub).execute(session,draft.id)
        operation=await create_operation(session,result.id,action='UPDATE',latitude=.001,longitude=.001)
    async def execute():
        async with SessionFactory() as session:
            try:return await execute_operation(session,UUID(operation['id']),pub)
            except ValueError:return None
    results=await asyncio.gather(execute(),execute())
    assert pub.calls==1 and sum(value is not None for value in results)==1
