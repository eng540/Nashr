"""Supported capabilities must remain publishable without running production."""
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.application.product_control_plane import ProductionProductControlPlaneService
from app.infrastructure.database.models import ProductionJobModel
from app.infrastructure.database.session import SessionFactory

@pytest.mark.asyncio
@pytest.mark.parametrize('source_key', ['ARABIC_LITERATURE_THEMATIC_TEXT','ARABIC_LITERATURE_DESIGN_CARD'])
async def test_supported_product_can_derive_and_publish_without_generation(source_key,monkeypatch):
    class Storage:
        async def ensure_available(self): pass
    monkeypatch.setattr('app.application.product_control_plane.S3ArtifactStorage.from_environment',lambda:Storage())
    async with SessionFactory() as session:
        service=ProductionProductControlPlaneService(session)
        products=await service.list_products()
        source=next((p for p in products if p['key']==source_key),None)
        assert source is not None, [p['key'] for p in products]
        before=await service.get_product(source_key)
        count=(await session.execute(select(func.count()).select_from(ProductionJobModel))).scalar_one()
        derived=await service.derive_product(source_key,source['active_version'],'TEST_SUPPORTED_'+uuid4().hex.upper(),'Supported derived product','Verify publication only')
        published=await service.publish(derived['key'],1)
        assert published['status']=='PUBLISHED'
        assert published['definition']['component_versions']==next(v for v in before['versions'] if v['version']==source['active_version'])['definition']['component_versions']
        assert await service.get_product(source_key)==before
        assert (await session.execute(select(func.count()).select_from(ProductionJobModel))).scalar_one()==count

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_mode', ['wrong_kind', 'wrong_mime', 'mixed_stages'])
async def test_card_publication_rejects_invalid_contract_or_recipe_before_storage(invalid_mode, monkeypatch):
    from app.application.output_contract_control_plane import OutputContractControlPlaneService
    from app.application.recipe_control_plane import ProductionRecipeControlPlaneService
    def unexpected_storage():
        pytest.fail('Invalid product must be rejected before any storage access')
    monkeypatch.setattr('app.application.product_control_plane.S3ArtifactStorage.from_environment', unexpected_storage)
    async with SessionFactory() as session:
        service = ProductionProductControlPlaneService(session)
        source = await service.get_product('ARABIC_LITERATURE_DESIGN_CARD')
        active = next(v for v in source['versions'] if v['status'] == 'PUBLISHED')
        definition = dict(active['definition'])
        definition.pop('component_versions')
        if invalid_mode == 'wrong_kind':
            definition['output_contract_key'] = 'TEXT_ARTIFACT'
        elif invalid_mode == 'wrong_mime':
            contracts = OutputContractControlPlaneService(session)
            key = 'TEST_JPEG_' + uuid4().hex.upper()
            await contracts.create_contract(key, 'JPEG test', 'Reject PNG renderer mismatch', {
                'artifact_kind': 'IMAGE', 'mime_type': 'image/jpeg', 'content_mode': 'STORAGE_URI',
                'required_metadata_fields': [], 'max_content_chars': None
            })
            await contracts.publish(key, 1)
            definition['output_contract_key'] = key
        else:
            recipes = ProductionRecipeControlPlaneService(session)
            recipe = await recipes.get_recipe(definition['recipe_key'])
            stages = next(v for v in recipe['versions'] if v['status'] == 'PUBLISHED')['stages']
            key = 'TEST_MIXED_' + uuid4().hex.upper()
            await recipes.create_recipe(key, 'Mixed card test', 'Reject unrelated stages', [
                {'key': 'unrelated', 'capability_key': 'produce_post', 'capability_version': 1}, *stages
            ])
            await recipes.publish(key, 1)
            definition['recipe_key'] = key
        key = 'TEST_INVALID_CARD_' + uuid4().hex.upper()
        await service.create_product(key, 'Invalid card test', 'Reject before activation', definition)
        with pytest.raises(ValueError, match='incompatible|image/png|only render_approved_text_card'):
            await service.publish(key, 1)
        assert (await service.get_product(key))['active_version'] is None
        assert await service.get_product(source['key']) == source
