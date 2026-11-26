"""Create synthetic disposable PostgreSQL fixtures and run the recovery drill."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pg-bin',type=Path,required=True)
parser.add_argument('--report-dir',type=Path,required=True)
args=parser.parse_args()
BIN=args.pg_bin.resolve()
OUT=args.report_dir.resolve()
OUT.mkdir(parents=True,exist_ok=True)
from scripts.recovery_drill import drill, connection, sql

with tempfile.TemporaryDirectory(prefix='nashr-fresh-recovery-') as temp:
 root=Path(temp);pg=root/'pg';log=root/'postgres.log'
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 subprocess.run([str(BIN/'initdb'),'-D',str(pg),'-U','postgres','--auth=trust','--no-locale','-E','UTF8'],check=True,capture_output=True)
 subprocess.run([str(BIN/'pg_ctl'),'-D',str(pg),'-l',str(log),'-o',f'-h 127.0.0.1 -p {port}','-w','start'],check=True,capture_output=True)
 try:
  admin=f'postgresql://postgres@127.0.0.1:{port}/postgres'
  for db in ['recovery_drill_source','recovery_drill_restore']:
   sql(BIN,connection(admin),f'CREATE DATABASE {db}')
  source=f'postgresql://postgres@127.0.0.1:{port}/recovery_drill_source'
  target=f'postgresql://postgres@127.0.0.1:{port}/recovery_drill_restore'
  env={**os.environ,'DATABASE_URL':source}
  result=subprocess.run([sys.executable,'scripts/migrate.py'],cwd=ROOT,env=env,capture_output=True,text=True)
  (OUT/'migration.log').write_text(result.stdout+result.stderr)
  if result.returncode:raise RuntimeError('Migrations failed')
  fixtures=root/'fixtures';(fixtures/'local-sources').mkdir(parents=True);(fixtures/'object-store/artifacts/drill').mkdir(parents=True)
  pdf=b'%PDF-1.4\n% synthetic recovery fixture, not user content\n%%EOF\n'
  media=b'SYNTHETIC OBJECT BYTES, not a playable video'
  local=fixtures/'local-sources/legacy.pdf';local.write_bytes(pdf)
  (fixtures/'object-store/artifacts/drill/video.mp4').write_bytes(media)
  from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
  from sqlalchemy import select
  from app.infrastructure.database.models import SourceModel,KnowledgeUnitModel,PostModel,ArtifactModel,PublicationModel,ScheduleModel,ScheduleItemModel
  payload_path=root/'rehydrated/payload.pdf'
  async def seed():
   engine=create_async_engine(source.replace('postgresql://','postgresql+asyncpg://'))
   async with async_sessionmaker(engine,expire_on_commit=False)() as s:
    src=SourceModel(filename='مصدر تجريبي.pdf',mime_type='application/pdf',storage_path=str(payload_path),size_bytes=len(pdf),status='STORED',file_payload=pdf,content_sha256=hashlib.sha256(pdf).hexdigest())
    legacy=SourceModel(filename='legacy.pdf',mime_type='application/pdf',storage_path=str(local),size_bytes=len(pdf),status='STORED',file_payload=None)
    s.add_all([src,legacy]);await s.flush()
    ku=KnowledgeUnitModel(source_id=src.id,position=1,title='معرفة تجريبية',content='نص المصدر الأصلي',original_text='نص المصدر الأصلي');s.add(ku);await s.flush()
    post=PostModel(knowledge_unit_id=ku.id,content='أصل محفوظ لا يقص',status='APPROVED',review_note='مراجعة تجريبية');s.add(post)
    artifact=ArtifactModel(source_knowledge_unit_id=ku.id,kind='VIDEO',status='AVAILABLE',storage_uri='s3://synthetic-recovery/artifacts/drill/video.mp4',mime_type='video/mp4',review_status='APPROVED',artifact_metadata={'sha256':hashlib.sha256(media).hexdigest(),'purpose':'isolated synthetic fixture'});s.add(artifact);await s.flush()
    pub=PublicationModel(knowledge_unit_id=ku.id,post_id=post.id,platform='telegram',destination='synthetic-never-send',content='نسخة منفصلة',status='PUBLISHED',external_id='synthetic-message-not-real');s.add(pub)
    schedule=ScheduleModel(name='خطة مكتملة تجريبية',status='COMPLETED',timezone='Asia/Riyadh');s.add(schedule);await s.flush()
    from datetime import datetime,timezone
    s.add(ScheduleItemModel(schedule_id=schedule.id,post_id=post.id,position=1,scheduled_at=datetime.now(timezone.utc),status='PUBLISHED',publication_id=pub.id,attempts=1))
    await s.commit();ids=(str(src.id),str(legacy.id))
   await engine.dispose()
   return ids
  source_id,legacy_id=asyncio.run(seed())
  report=drill(source,target,fixtures,BIN,OUT/'round-trip.json')
  # Export reduced inventory from the restored isolated database only.
  from scripts.recovery_inventory_export import export
  from scripts.recovery_coverage import coverage
  reduced_path=root/'reduced-inventory.json'
  reduced=export(target,BIN,reduced_path)
  assert reduced['snapshot']['source_rows']==2 and reduced['snapshot']['artifact_rows']==1
  assert reduced['snapshot']['derivative_rows']==0
  assert reduced_path.stat().st_mode & 0o777 == 0o600
  assert 'نص المصدر الأصلي' not in reduced_path.read_text()
  try:export(target,BIN,reduced_path)
  except FileExistsError:overwrite_refused=True
  else:raise AssertionError('Inventory output overwrite accepted')
  ro_env=connection(target);ro_env['PGOPTIONS']='-c default_transaction_read_only=on'
  try:sql(BIN,ro_env,'CREATE TABLE forbidden_export_write(id integer)')
  except RuntimeError:readonly_enforced=True
  else:raise AssertionError('Read-only mode did not reject write')
  copied_objects=root/'coverage-objects/synthetic-recovery/artifacts/drill'
  copied_objects.mkdir(parents=True)
  (copied_objects/'video.mp4').write_bytes(media)
  coverage_report=coverage(reduced,root,root/'coverage-objects')
  assert coverage_report['blocking_gaps']==0 and coverage_report['object_count']==1
  (copied_objects/'video.mp4').unlink()
  missing_report=coverage(reduced,root,root/'coverage-objects')
  assert missing_report['blocking_gaps']==1
  export_checks={'source_rows':2,'artifact_rows':1,'derivative_rows':0,
    'private_output_mode':True,'content_bodies_omitted':True,
    'overwrite_refused':overwrite_refused,'readonly_enforced':readonly_enforced,
    'coverage_no_detected_gaps':True,'missing_object_detected':True,
    'live_production_export':False,'durable_backup_created':False}
  (OUT/'inventory-export-checks.json').write_text(json.dumps(export_checks,indent=2)+'\n')
  async def rehydrate():
   engine=create_async_engine(target.replace('postgresql://','postgresql+asyncpg://'))
   try:
    async with async_sessionmaker(engine)() as s:
     src=await s.get(SourceModel,uuid.UUID(source_id));assert not payload_path.exists();assert src.ensure_file_on_disk().read_bytes()==pdf
     legacy=await s.get(SourceModel,uuid.UUID(legacy_id));local.unlink()
     try:legacy.ensure_file_on_disk()
     except FileNotFoundError:legacy_missing_detected=True
     else:raise AssertionError('Missing legacy file undetected')
     return {'db_payload_rehydration':True,'legacy_missing_payload_and_file_fails':legacy_missing_detected,'external_network_calls':0,'application_scheduler_started':False,'restored_app_serving_tested':False,'actual_s3_transport_tested':False,'actual_live_rows_tested':False}
   finally:await engine.dispose()
  checks=asyncio.run(rehydrate());(OUT/'semantic-checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(checks)
  # A second run must fail closed because target now has data.
  try:drill(source,target,fixtures,BIN,OUT/'should-not-exist.json')
  except ValueError as e:
   assert 'not empty' in str(e);(OUT/'safety-checks.json').write_text(json.dumps({'nonempty_target_refused':True},indent=2)+'\n')
  else:raise AssertionError('Nonempty target accepted')
 finally:
  subprocess.run([str(BIN/'pg_ctl'),'-D',str(pg),'-m','fast','-w','stop'],check=True,capture_output=True)
print('Fresh isolated PostgreSQL stopped; temporary dump/fixtures removed. Reports only retained.')
