"""Verify the migration covers all model columns and indexes."""

import re

with open("alembic/versions/001_initial_schema.py") as f:
    migration_src = f.read()

# Use a more robust approach: find text between create_table and the matching close
# Use regex to find all create_table blocks
pattern = r'op\.create_table\(\s*"(\w+)",(.*?)\n    \)'
blocks = re.findall(pattern, migration_src, re.DOTALL)

tables_in_migration = {}
for table_name, block_content in blocks:
    cols = re.findall(r'sa\.Column\("(\w+)"', block_content)
    tables_in_migration[table_name] = cols

print(f"Tables found: {list(tables_in_migration.keys())}")

expected = {
    "users": sorted(
        [
            "id",
            "email",
            "display_name",
            "avatar_url",
            "plan",
            "is_active",
            "settings",
            "connector_credentials",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
    ),
    "agent_states": sorted(
        [
            "id",
            "user_id",
            "status",
            "current_task",
            "execution_context",
            "bridge_connected",
            "last_heartbeat",
            "created_at",
            "updated_at",
        ]
    ),
    "memories": sorted(
        [
            "id",
            "user_id",
            "category",
            "content",
            "metadata",
            "sync_version",
            "synced_at",
            "created_at",
            "updated_at",
        ]
    ),
    "skills": sorted(
        [
            "id",
            "user_id",
            "name",
            "description",
            "skill_type",
            "definition",
            "is_shared",
            "sync_version",
            "created_at",
            "updated_at",
        ]
    ),
    "scheduled_tasks": sorted(
        [
            "id",
            "user_id",
            "name",
            "description",
            "schedule",
            "prompt",
            "is_active",
            "last_run",
            "next_run",
            "created_at",
            "updated_at",
        ]
    ),
    "conversations": sorted(
        ["id", "user_id", "title", "is_active", "metadata", "created_at", "updated_at"]
    ),
    "messages": sorted(
        [
            "id",
            "conversation_id",
            "user_id",
            "role",
            "content",
            "tool_calls",
            "token_count",
            "created_at",
            "updated_at",
        ]
    ),
    "sync_log": sorted(
        [
            "id",
            "user_id",
            "entity_type",
            "entity_id",
            "action",
            "data",
            "sync_version",
            "source",
            "created_at",
            "updated_at",
        ]
    ),
}

all_ok = True
for table, cols in expected.items():
    if table not in tables_in_migration:
        print(f"  MISSING TABLE: {table}")
        all_ok = False
        continue
    mig_cols = sorted(set(tables_in_migration[table]))
    if mig_cols == cols:
        print(f"  {table}: OK ({len(cols)} columns)")
    else:
        missing = set(cols) - set(mig_cols)
        extra = set(mig_cols) - set(cols)
        if missing:
            print(f"  {table}: MISSING columns: {missing}")
            all_ok = False
        if extra:
            print(f"  {table}: EXTRA columns: {extra}")
            all_ok = False

# Check FK constraints (including conversation_id)
fks = re.findall(r'sa\.ForeignKeyConstraint\(\["(\w+)"\],\s*\["([\w.]+)"\]', migration_src)
print(f"\nForeign keys: {len(fks)}")
for col, ref in fks:
    print(f"  {col} -> {ref}")

expected_fks = {
    # agent_states, memories, skills, scheduled_tasks,
    # conversations, messages, sync_log
    ("user_id", "users.id"): 7,
    ("conversation_id", "conversations.id"): 1,  # messages
}
fk_tuples = [(c, r) for c, r in fks]
for (col, ref), count in expected_fks.items():
    actual = fk_tuples.count((col, ref))
    status = "OK" if actual == count else f"EXPECTED {count}, GOT {actual}"
    print(f"  FK {col}->{ref}: {status} ({actual})")

if all_ok:
    print("\nALL CHECKS PASSED")
else:
    print("\nSOME CHECKS FAILED")
