"""categories

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 19:29:20.716411
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

# Built-in categories: (key, name, kind, color, icon, [(key, name, icon), ...]).
# Frozen here on purpose: later edits happen in the app, not by changing this list.
DEFAULTS = [
    ("boende", "Boende & hushåll", "expense", "blue", "house", [
        ("boende.hyra", "Hyra / avgift", "key-round"),
        ("boende.bolan", "Bolån (ränta & amortering)", "landmark"),
        ("boende.el", "El & värme", "zap"),
        ("boende.vatten", "Vatten & sophämtning", "droplet"),
        ("boende.forsakring", "Hemförsäkring", "shield-check"),
        ("boende.larm", "Hemlarm & säkerhet", "siren"),
        ("boende.stad", "Hemstäd & hushållstjänster", "spray-can"),
        ("boende.internet", "Internet & TV", "wifi"),
        ("boende.underhall", "Underhåll & renovering", "hammer"),
        ("boende.inredning", "Möbler & inredning", "sofa"),
        ("boende.husdjur", "Husdjur", "paw-print"),
    ]),
    ("mat", "Mat & dryck", "expense", "orange", "utensils", [
        ("mat.livsmedel", "Livsmedel", "shopping-basket"),
        ("mat.restaurang", "Restaurang, café & bar", "coffee"),
        ("mat.snabbmat", "Snabbmat & takeaway", "sandwich"),
        ("mat.alkohol", "Alkohol", "wine"),
    ]),
    ("transport", "Transport", "expense", "teal", "bus", [
        ("transport.kollektivtrafik", "Kollektivtrafik", "train-front"),
        ("transport.bilpool", "Bilpool & hyrbil", "car"),
        ("transport.taxi", "Taxi & samåkning", "car-taxi-front"),
        ("transport.cykel", "Cykel & elsparkcykel", "bike"),
    ]),
    ("shopping", "Shopping", "expense", "pink", "shopping-bag", [
        ("shopping.klader", "Kläder & skor", "shirt"),
        ("shopping.elektronik", "Elektronik", "smartphone"),
        ("shopping.hem", "Hem & trädgård", "flower-2"),
        ("shopping.ovrigt", "Övrig shopping", "package"),
    ]),
    ("halsa", "Hälsa & välmående", "expense", "red", "heart-pulse", [
        ("halsa.vard", "Vård & tandvård", "stethoscope"),
        ("halsa.apotek", "Apotek", "pill"),
        ("halsa.traning", "Träning & gym", "dumbbell"),
        ("halsa.skonhet", "Skönhet & frisör", "scissors"),
    ]),
    ("noje", "Nöje & fritid", "expense", "purple", "ticket", [
        ("noje.streaming", "Streaming & prenumerationer", "tv"),
        ("noje.spel", "TV- & datorspel", "gamepad-2"),
        ("noje.evenemang", "Evenemang & kultur", "music"),
        ("noje.hobby", "Hobby & sport", "trophy"),
        ("noje.bocker", "Böcker & tidningar", "book-open"),
    ]),
    ("resor", "Resor", "expense", "sky", "plane", [
        ("resor.flyg", "Flyg & tåg", "plane"),
        ("resor.boende", "Boende", "bed"),
        ("resor.ovrigt", "Aktiviteter & övrigt", "map"),
    ]),
    ("ekonomi", "Ekonomi & avgifter", "expense", "slate", "receipt", [
        ("ekonomi.bankavgifter", "Bankavgifter", "landmark"),
        ("ekonomi.lan", "Övriga lån & krediter", "credit-card"),
        ("ekonomi.forsakringar", "Försäkringar", "umbrella"),
        ("ekonomi.skatt", "Skatt", "file-text"),
        ("ekonomi.fack", "Fackavgift & a-kassa", "users"),
    ]),
    ("gavor", "Gåvor & bidrag", "expense", "amber", "gift", [
        ("gavor.presenter", "Presenter", "gift"),
        ("gavor.valgorenhet", "Välgörenhet", "hand-heart"),
    ]),
    ("inkomster", "Inkomster", "income", "green", "wallet", [
        ("inkomster.lon", "Lön", "briefcase"),
        ("inkomster.ersattningar", "Ersättningar", "hand-coins"),
        ("inkomster.aterbetalningar", "Återbetalningar & återköp", "rotate-ccw"),
        ("inkomster.ranta", "Ränta & utdelning", "trending-up"),
        ("inkomster.ovrigt", "Swish in / övrigt", "arrow-down-left"),
    ]),
    ("delat", "Delade utgifter", "reimbursement", "lime", "heart-handshake", [
        ("delat.partner", "Ersättning från partner", "heart-handshake"),
    ]),
    ("overforingar", "Sparande & överföringar", "transfer", "brown", "arrow-left-right", [
        ("overforingar.egna", "Överföring mellan egna konton", "arrow-left-right"),
        ("overforingar.sparande", "Sparande & investeringar", "piggy-bank"),
        ("overforingar.kreditkort", "Betalning av kreditkortsfaktura", "credit-card"),
    ]),
    ("ovrigt", "Övrigt", "expense", "gray", "ellipsis", [
        ("ovrigt.kontantuttag", "Kontantuttag", "banknote"),
        ("ovrigt.swish", "Swish ut", "arrow-up-right"),
    ]),
]


def upgrade() -> None:
    categories = op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('key', sa.String(length=50), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_source', sa.String(length=10), nullable=True))
        batch_op.create_foreign_key('fk_transactions_category_id', 'categories', ['category_id'], ['id'],
                                    ondelete='SET NULL')

    rows = []
    next_id = 1
    for i, (key, name, kind, color, icon, children) in enumerate(DEFAULTS):
        parent_id = next_id
        rows.append({"id": parent_id, "parent_id": None, "key": key, "name": name, "kind": kind,
                     "color": color, "icon": icon, "sort_order": i})
        next_id += 1
        for j, (ckey, cname, cicon) in enumerate(children):
            rows.append({"id": next_id, "parent_id": parent_id, "key": ckey, "name": cname, "kind": kind,
                         "color": None, "icon": cicon, "sort_order": j})
            next_id += 1
    op.bulk_insert(categories, rows)


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_category_id', type_='foreignkey')
        batch_op.drop_column('category_source')

    op.drop_table('categories')
