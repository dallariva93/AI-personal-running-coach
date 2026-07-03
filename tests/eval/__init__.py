"""Coach eval harness (Roadmap A9 / Passo 9).

Synthetic athletes + a day-by-day simulator that runs the *real* coaching
pipeline (decision engine, adaptive plan, execution scoring) over a temporary
database, plus deterministic safety assertions. From here on no change to the
prompts/engine ships without these scenarios staying green.
"""
