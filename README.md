# QMT — Quality Movement Training

Rezervacija termina za QMT: klijenti rezerviraju mjesta u tjednom rasporedu,
trener upravlja rasporedom i vidi polaznike po terminu.

## Pokretanje (lokalno)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
createdb qmt
alembic upgrade head
python scripts/seed_demo.py     # demo korisnici + raspored
python serve.py                 # http://127.0.0.1:8100
```

Demo prijave: `trener@qmt.local` / `trener123` (admin) · `ivan@qmt.local` /
`lozinka123` · `ana@qmt.local` / `lozinka123`.

## Testovi

```bash
createdb qmt_test   # jednom
pytest -q
```

Detalji arhitekture i konvencije: [CLAUDE.md](CLAUDE.md).
