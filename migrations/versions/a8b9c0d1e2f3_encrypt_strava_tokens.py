"""encrypt Strava OAuth tokens at rest (A10)

Widens access_token/refresh_token to Text (Fernet ciphertext is ~200 chars vs
the old VARCHAR(128)) and encrypts existing plaintext values in place. The
data step is idempotent: encrypted values carry an "enc:" prefix and are
skipped, so re-running (or running on an empty/fresh DB) is a no-op.

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-07-03 09:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strava_accounts") as batch:
        batch.alter_column(
            "access_token", existing_type=sa.String(length=128), type_=sa.Text()
        )
        batch.alter_column(
            "refresh_token", existing_type=sa.String(length=128), type_=sa.Text()
        )

    # Encrypt rows written before this revision. Imports the app's crypto module
    # (rather than inlining a copy) so key resolution cannot drift between the
    # migration and the runtime — a mismatch would make tokens undecryptable.
    from app.security.crypto import encrypt_secret, is_encrypted

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, access_token, refresh_token FROM strava_accounts")
    ).fetchall()
    for row_id, access, refresh in rows:
        updates = {}
        if access and not is_encrypted(access):
            updates["access_token"] = encrypt_secret(access)
        if refresh and not is_encrypted(refresh):
            updates["refresh_token"] = encrypt_secret(refresh)
        if updates:
            sets = ", ".join(f"{col} = :{col}" for col in updates)
            conn.execute(
                sa.text(f"UPDATE strava_accounts SET {sets} WHERE id = :id"),
                {**updates, "id": row_id},
            )


def downgrade() -> None:
    from app.security.crypto import decrypt_secret, is_encrypted

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, access_token, refresh_token FROM strava_accounts")
    ).fetchall()
    for row_id, access, refresh in rows:
        updates = {}
        if is_encrypted(access):
            updates["access_token"] = decrypt_secret(access)
        if is_encrypted(refresh):
            updates["refresh_token"] = decrypt_secret(refresh)
        if updates:
            sets = ", ".join(f"{col} = :{col}" for col in updates)
            conn.execute(
                sa.text(f"UPDATE strava_accounts SET {sets} WHERE id = :id"),
                {**updates, "id": row_id},
            )

    with op.batch_alter_table("strava_accounts") as batch:
        batch.alter_column(
            "access_token", existing_type=sa.Text(), type_=sa.String(length=128)
        )
        batch.alter_column(
            "refresh_token", existing_type=sa.Text(), type_=sa.String(length=128)
        )
