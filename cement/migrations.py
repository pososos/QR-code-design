"""Tiny schema-evolution helper; there is no formal migration framework yet.

Every table is still created with CREATE TABLE IF NOT EXISTS at the top of each module's
schema(); this only covers adding a column to a table that may already exist from before
that column was introduced. Column removal or type changes still need a manual plan.
"""


def ensure_column(db, table, column, declaration):
    columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
    if column not in columns:
        db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')
