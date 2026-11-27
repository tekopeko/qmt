"""a gym training is blocks: Stanica and Kružni set; two templates

Build 1 of roadmap/2026-11-27-dvoranski-treninzi-plan.md (27.11.2026). The
owner: "A gym training consists of 'Stanica' and 'Kružni set' where the
'Kružni set' consists of 4 of 'Krug' at default which can be changed." …
"yes, these named parts disappear for now for the gym trainings." … "In the
start, there would be two templates. One is 'Stanični' with 6 'Stanica' in a
row […] The second template is a training plan with Stanica first and then
Kružni part and the Kružni part has 4 'Krug' parts by default".

1. gym_training_blocks: a training's blocks (training_id → gym_trainings
   CASCADE, indexed), each in its place (position, unique in the training,
   DEFERRABLE INITIALLY DEFERRED), its kind ('stanica' or 'kruzni', a
   CHECK), a Kružni set's number of Krug (rounds 1–20, NULL for a Stanica,
   a CHECK) and its pause after a Krug (rest_seconds 0–3600 or NULL, a
   CHECK), and the block's rating (effort 1–10 or NULL, a CHECK).
2. gym_training_items: block_id joins (→ gym_training_blocks CASCADE, NOT
   NULL, indexed); position is its place in its block (unique per block,
   uq_gym_training_items_block_position, deferred; the per-training
   uq_gym_training_items_position goes); section and its CHECK go, and so
   does effort (the block holds the rating). training_id stays.
3. gym_training_parts goes (the parts' own names and circuits).
4. gym_templates (title String(80), position unique deferred) and
   gym_template_blocks (template_id CASCADE, position unique per template
   deferred, kind, slots = a Kružni set's rows 1–12, rounds 1–20, rest
   0–3600; NULL for a Stanica), and the two the owner asked for: "Stanični
   trening" (six Stanica) and "Kružni trening" (a Stanica, then a Kružni set
   of 4 rows, 4 Krug, no pause). This file's own copy of them
   (copy.GYM_TEMPLATES is the code's, which the dev seed puts back).

The trainings there are converted (prod holds three, made on 27.11., none
ticked): per training its items in models.SECTIONS' order, then by place; a
part that is a circuit (a gym_training_parts row with rounds) becomes ONE
Kružni set, its rounds and its rest, its rating the first rating its items
hold, holding its items in their order; every other item, a slot too, is a
Stanica of its own, its rating the item's. Sets, their rounds and their
times stay as they were. Part names are let go.

Downgrade, as far as the old shape can say it: every Stanica's item into
'trening', in order; the first Kružni set's items into 'trening_b' (a
circuit part of its rounds and rest), a second's into 'trening_c', any
further set's items after it there; the ratings back on the items (a
Kružni set's on each of its exercises); the template tables dropped. What
it cannot restore: the blocks' order across kinds (the stations come first,
then the sets), a Kružni set of one Krug as a circuit (the old circuits had
two at least: its part is a normal one), a third or later set's own rounds
and rest, the parts' names (gone at the upgrade), a rating on a block that
holds no exercise, and the templates.

Revision ID: 9b4e2d7f1c58
Revises: 3d9a6f2c8b51
Create Date: 2026-11-27 12:00:00.000000

"""
from itertools import groupby
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b4e2d7f1c58'
down_revision: Union[str, Sequence[str], None] = '3d9a6f2c8b51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SECTIONS = ("zagrijavanje", "trening", "trening_b", "trening_c", "istezanje")   # models.SECTIONS' keys, the old shape's
# the two templates, this revision's copy (copy.GYM_TEMPLATES is the code's):
# (title, ((kind, slots, rounds, rest_seconds), …))
TEMPLATES = (
    ("Stanični trening", tuple(("stanica", None, None, None) for _ in range(6))),
    ("Kružni trening", (("stanica", None, None, None), ("kruzni", 4, 4, None))),
)


def _templates(conn) -> None:
    """The two templates, in their order."""
    for n, (title, blocks) in enumerate(TEMPLATES, start=1):
        tid = conn.execute(sa.text("INSERT INTO gym_templates (title, position) VALUES (:t, :n) RETURNING id"),
                           {"t": title, "n": n}).scalar_one()
        for k, (kind, slots, rounds, rest) in enumerate(blocks, start=1):
            conn.execute(sa.text("INSERT INTO gym_template_blocks (template_id, position, kind, slots, rounds, "
                                 "rest_seconds) VALUES (:t, :k, :kind, :s, :r, :rest)"),
                         {"t": tid, "k": k, "kind": kind, "s": slots, "r": rounds, "rest": rest})


def _rating(value):
    """A rating the blocks' CHECK takes (1–10), else none."""
    return value if type(value) is int and 1 <= value <= 10 else None


def _to_blocks(conn) -> None:
    """Every training's items made blocks (the module's docstring)."""
    circuits = {(t, s): (r, rest) for t, s, r, rest in conn.execute(sa.text(
        "SELECT training_id, section, rounds, rest_seconds FROM gym_training_parts WHERE rounds IS NOT NULL"))}
    order = {key: n for n, key in enumerate(SECTIONS)}
    rows = conn.execute(sa.text("SELECT id, training_id, section, position, effort FROM gym_training_items")).all()
    rows = sorted(rows, key=lambda r: (r.training_id, order.get(r.section, len(order)), r.position, r.id))

    def block(training_id, position, kind, rounds, rest, effort) -> int:
        return conn.execute(sa.text(
            "INSERT INTO gym_training_blocks (training_id, position, kind, rounds, rest_seconds, effort) "
            "VALUES (:t, :p, :k, :r, :rest, :e) RETURNING id"),
            {"t": training_id, "p": position, "k": kind, "r": rounds, "rest": rest, "e": effort}).scalar_one()

    def place(item_id, block_id, position) -> None:
        conn.execute(sa.text("UPDATE gym_training_items SET block_id = :b, position = :p WHERE id = :i"),
                     {"b": block_id, "p": position, "i": item_id})

    for training_id, items in groupby(rows, key=lambda r: r.training_id):
        n = 0
        for section, part in groupby(items, key=lambda r: r.section):
            part = list(part)
            circuit = circuits.get((training_id, section))
            if circuit is not None:
                n += 1
                effort = next((_rating(r.effort) for r in part if _rating(r.effort) is not None), None)
                bid = block(training_id, n, "kruzni", circuit[0], circuit[1], effort)
                for k, r in enumerate(part, start=1):
                    place(r.id, bid, k)
                continue
            for r in part:
                n += 1
                place(r.id, block(training_id, n, "stanica", None, None, _rating(r.effort)), 1)


def upgrade() -> None:
    """Upgrade schema: blocks, the items in them, the two templates; the parts go."""
    # the per-training place goes first: a deferred constraint with checks
    # pending would refuse every ALTER TABLE after the rows change
    op.drop_constraint('uq_gym_training_items_position', 'gym_training_items', type_='unique')
    op.create_table(
        'gym_training_blocks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('training_id', sa.Integer(), sa.ForeignKey('gym_trainings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('rounds', sa.Integer(), nullable=True),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.Column('effort', sa.Integer(), nullable=True),
        sa.UniqueConstraint('training_id', 'position', name='uq_gym_training_blocks_position',
                            deferrable=True, initially='DEFERRED'),
        sa.CheckConstraint("kind IN ('stanica', 'kruzni')", name='ck_gym_training_blocks_kind'),
        sa.CheckConstraint('rounds BETWEEN 1 AND 20', name='ck_gym_training_blocks_rounds'),
        sa.CheckConstraint('rest_seconds BETWEEN 0 AND 3600', name='ck_gym_training_blocks_rest_seconds'),
        sa.CheckConstraint('effort BETWEEN 1 AND 10', name='ck_gym_training_blocks_effort'),
    )
    op.create_index('ix_gym_training_blocks_training_id', 'gym_training_blocks', ['training_id'])
    # the items' key to their block, made before any block is (its FK too)
    op.add_column('gym_training_items', sa.Column('block_id', sa.Integer(), nullable=True))
    op.create_foreign_key('gym_training_items_block_id_fkey', 'gym_training_items', 'gym_training_blocks',
                          ['block_id'], ['id'], ondelete='CASCADE')
    op.create_table(
        'gym_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.UniqueConstraint('position', name='uq_gym_templates_position', deferrable=True, initially='DEFERRED'),
    )
    op.create_table(
        'gym_template_blocks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('gym_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('slots', sa.Integer(), nullable=True),
        sa.Column('rounds', sa.Integer(), nullable=True),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.UniqueConstraint('template_id', 'position', name='uq_gym_template_blocks_position',
                            deferrable=True, initially='DEFERRED'),
        sa.CheckConstraint("kind IN ('stanica', 'kruzni')", name='ck_gym_template_blocks_kind'),
        sa.CheckConstraint('slots BETWEEN 1 AND 12', name='ck_gym_template_blocks_slots'),
        sa.CheckConstraint('rounds BETWEEN 1 AND 20', name='ck_gym_template_blocks_rounds'),
        sa.CheckConstraint('rest_seconds BETWEEN 0 AND 3600', name='ck_gym_template_blocks_rest_seconds'),
    )
    op.create_index('ix_gym_template_blocks_template_id', 'gym_template_blocks', ['template_id'])
    conn = op.get_bind()
    _templates(conn)
    _to_blocks(conn)
    conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))       # the rows' checks now, before the tables change
    op.alter_column('gym_training_items', 'block_id', existing_type=sa.Integer(), nullable=False)
    op.create_index('ix_gym_training_items_block_id', 'gym_training_items', ['block_id'])
    op.create_unique_constraint('uq_gym_training_items_block_position', 'gym_training_items', ['block_id', 'position'],
                                deferrable=True, initially='DEFERRED')
    op.drop_constraint('ck_gym_training_items_section', 'gym_training_items', type_='check')
    op.drop_column('gym_training_items', 'section')
    op.drop_column('gym_training_items', 'effort')
    op.drop_table('gym_training_parts')


def _to_parts(conn) -> None:
    """Every training's blocks made parts again (the module's docstring)."""
    blocks = conn.execute(sa.text("SELECT id, training_id, position, kind, rounds, rest_seconds, effort "
                                  "FROM gym_training_blocks ORDER BY training_id, position, id")).all()
    items = conn.execute(sa.text("SELECT id, block_id, position, exercise_id, exercise_name FROM gym_training_items "
                                 "ORDER BY block_id, position, id")).all()
    by_block: dict[int, list] = {}
    for it in items:
        by_block.setdefault(it.block_id, []).append(it)
    for training_id, rows in groupby(blocks, key=lambda b: b.training_id):
        rows = list(rows)
        stations = [b for b in rows if b.kind != "kruzni"]
        sets = [b for b in rows if b.kind == "kruzni"]
        # (the section, the blocks whose items go there): stations, then the sets' parts
        laid = [("trening", stations)] + [("trening_b", sets[:1]), ("trening_c", sets[1:])]
        n = 0
        for section, group in laid:
            for b in group:
                for it in by_block.get(b.id, []):
                    n += 1
                    rated = b.effort if (it.exercise_id is not None or it.exercise_name) else None
                    conn.execute(sa.text("UPDATE gym_training_items SET section = :s, position = :p, effort = :e "
                                         "WHERE id = :i"), {"s": section, "p": n, "e": rated, "i": it.id})
        for section, b in (("trening_b", sets[0] if sets else None), ("trening_c", sets[1] if len(sets) > 1 else None)):
            if b is not None and b.rounds is not None and 2 <= b.rounds <= 20:
                conn.execute(sa.text("INSERT INTO gym_training_parts (training_id, section, title, rounds, rest_seconds) "
                                     "VALUES (:t, :s, '', :r, :rest)"),
                             {"t": training_id, "s": section, "r": b.rounds, "rest": b.rest_seconds})


def downgrade() -> None:
    """Downgrade schema: the parts again, the items in them, no block, no template."""
    op.create_table(
        'gym_training_parts',
        sa.Column('training_id', sa.Integer(), sa.ForeignKey('gym_trainings.id', ondelete='CASCADE'),
                  primary_key=True, autoincrement=False),
        sa.Column('section', sa.String(length=12), primary_key=True),
        sa.Column('title', sa.String(length=60), server_default=sa.text("''"), nullable=False),
        sa.Column('rounds', sa.Integer(), nullable=True),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
        sa.CheckConstraint('rounds BETWEEN 2 AND 20', name='ck_gym_training_parts_rounds'),
        sa.CheckConstraint('rest_seconds BETWEEN 0 AND 3600', name='ck_gym_training_parts_rest_seconds'),
    )
    op.add_column('gym_training_items', sa.Column('section', sa.String(length=12), server_default=sa.text("'trening'"),
                                                  nullable=False))
    op.add_column('gym_training_items', sa.Column('effort', sa.Integer(), nullable=True))
    # the per-block place goes before the rows change (a deferred constraint's checks pending refuse an ALTER)
    op.drop_constraint('uq_gym_training_items_block_position', 'gym_training_items', type_='unique')
    conn = op.get_bind()
    _to_parts(conn)
    conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
    op.create_unique_constraint('uq_gym_training_items_position', 'gym_training_items', ['training_id', 'position'],
                                deferrable=True, initially='DEFERRED')
    op.create_check_constraint('ck_gym_training_items_section', 'gym_training_items',
                               "section IN (" + ", ".join(f"'{k}'" for k in SECTIONS) + ")")
    op.drop_index('ix_gym_training_items_block_id', table_name='gym_training_items')
    op.drop_constraint('gym_training_items_block_id_fkey', 'gym_training_items', type_='foreignkey')
    op.drop_column('gym_training_items', 'block_id')
    op.drop_table('gym_training_blocks')
    op.drop_table('gym_template_blocks')
    op.drop_table('gym_templates')
