        "prompt_template_versions",
        ["prompt_template_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PUBLISHED'"),
    )
    bind = op.get_bind()
    existing_template = bind.execute(
        sa.text("SELECT id FROM prompt_templates WHERE key = :key"),
        {"key": EDITORIAL_PROMPT_KEY},
    ).scalar_one_or_none()
    template_id = existing_template or uuid4()
    if existing_template is None:
        bind.execute(
            sa.text("INSERT INTO prompt_templates (id, key, name, purpose) VALUES (:id, :key, :name, :purpose)"),
            {"id": template_id, "key": EDITORIAL_PROMPT_KEY, "name": EDITORIAL_PROMPT_NAME, "purpose": EDITORIAL_PROMPT_PURPOSE},
        )
    existing_version = bind.execute(
        sa.text("SELECT id FROM prompt_template_versions WHERE prompt_template_id = :template_id AND version = 1"),
        {"template_id": template_id},
    ).scalar_one_or_none()
    if existing_version is None:
        bind.execute(
            sa.text("INSERT INTO prompt_template_versions (id, prompt_template_id, version, body, status) VALUES (:id, :template_id, 1, :body, 'PUBLISHED')"),
            {"id": uuid4(), "template_id": template_id, "body": EDITORIAL_PROMPT_BODY},
        )

def downgrade() -> None:
    op.drop_index("uq_prompt_template_versions_active", table_name="prompt_template_versions")
    op.drop_table("prompt_template_versions")
    op.drop_table("prompt_templates")