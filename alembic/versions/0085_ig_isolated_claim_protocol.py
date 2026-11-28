"""Isolated, unregistered protocol storage; no runtime relationship."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='0085_ig_isolated_claim_protocol'
down_revision='0084_ig_private_batch_prepare'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('instagram_isolated_controls',
        sa.Column('dispatch_id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('generation',sa.Integer(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('revoked',sa.Boolean(),nullable=False),sa.Column('pins_hash',sa.String(64),nullable=False),
        sa.Column('connection_generation',sa.String(64),nullable=False),
        sa.Column('decision_expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('grant_expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('grant_active',sa.Boolean(),nullable=False),sa.Column('reconcile_after',sa.DateTime(timezone=True)))
    op.create_table('instagram_isolated_claims',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('dispatch_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_isolated_controls.dispatch_id'),nullable=False),
        sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('token_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('kind',sa.String(10),nullable=False),sa.Column('write_step',sa.String(30)),
        sa.Column('state',sa.String(30),nullable=False),sa.Column('generation',sa.Integer(),nullable=False),
        sa.Column('control_version',sa.Integer(),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('worker_id',sa.String(100),nullable=False),sa.Column('result',pg.JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('dispatch_id','write_step',name='uq_ig_isolated_write_step'),
        sa.CheckConstraint("kind IN ('WRITE','READ')",name='ck_ig_isolated_claim_kind'),
        sa.CheckConstraint("state IN ('ACTIVE','COMPLETED','STOPPED_WITHOUT_WRITE','UNKNOWN','SUPERSEDED')",name='ck_ig_isolated_claim_state'))
    op.create_index('uq_ig_isolated_active_write','instagram_isolated_claims',['dispatch_id'],unique=True,postgresql_where=sa.text("kind='WRITE' AND state='ACTIVE'"))
    op.create_index('uq_ig_isolated_active_read','instagram_isolated_claims',['dispatch_id'],unique=True,postgresql_where=sa.text("kind='READ' AND state='ACTIVE'"))

    op.create_table('instagram_isolated_stops',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),sa.Column('request_key',sa.String(100),nullable=False,unique=True),
        sa.Column('scope_hash',sa.String(64),nullable=False),sa.Column('scope',pg.JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('instagram_isolated_stop_events',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('stop_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_isolated_stops.id'),nullable=False),
        sa.Column('dispatch_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_isolated_controls.dispatch_id'),nullable=False),
        sa.Column('claim_id',pg.UUID(as_uuid=True),sa.ForeignKey('instagram_isolated_claims.id')),
        sa.Column('sequence',sa.Integer(),nullable=False),sa.Column('outcome',sa.String(40),nullable=False),
        sa.Column('evidence',pg.JSONB(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('stop_id','dispatch_id','sequence',name='uq_ig_isolated_stop_sequence'))
    # Request scope and receipt history are immutable even to accidental ORM edits.
    op.execute("CREATE FUNCTION ig_isolated_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated protocol audit is append-only'; END $$")
    for table in ('instagram_isolated_stops','instagram_isolated_stop_events'):
        op.execute(f"CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ig_isolated_immutable()")

def downgrade():
    op.drop_table('instagram_isolated_stop_events');op.drop_table('instagram_isolated_stops')
    op.execute('DROP FUNCTION ig_isolated_immutable()')
    op.drop_table('instagram_isolated_claims');op.drop_table('instagram_isolated_controls')
