"""Offline chat over demo-data/ using a local Ollama model + DuckDB.

No network calls at runtime — everything (model inference, querying) happens
locally. The only online step is the one-time `ollama pull` of the models below,
done once while you have internet.

Usage:
    .venv/bin/python scripts/chat_with_data.py
    .venv/bin/python scripts/chat_with_data.py "Which department has the highest blocked-event rate?"

Requires:
    - `ollama serve` reachable at localhost:11434 (the Ollama app/daemon running)
    - SQL_MODEL and ANSWER_MODEL below pulled locally: `ollama pull qwen2.5-coder:7b`,
      `ollama pull llama3.1:8b` (or edit the constants to whatever you have via `ollama list`)
    - duckdb in this venv: `.venv/bin/pip install duckdb` (one-time, needs internet)

How it works: loads demo-data/*.csv + policies.json into in-memory DuckDB views
(matches docs/adr/0003-duckdb.md's choice of DuckDB as the analytics engine),
asks a local coding model to translate your question into SQL against that
schema, runs it, then asks a local chat model to summarize the result in plain
English. Text-to-SQL rather than embedding-based RAG because this data is
tabular/structured, not prose — SQL over real rows is far more reliable than
retrieval over chunked CSV rows for "which department..." / "how many..."
style questions.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA_DIR = PROJECT_ROOT / "demo-data"
OLLAMA_URL = "http://localhost:11434/api/generate"

SQL_MODEL = "qwen2.5-coder:7b"
ANSWER_MODEL = "llama3.1:8b"

CSV_TABLES = [
    "users",
    "departments",
    "applications",
    "ai_events",
    "models",
    "pricing",
    "billing_accounts",
    "sso_groups",
    "mcp_servers",
    "mcp_tool_calls",
    "incidents",
    "monthly_costs",
    "shadow_ai",
]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    missing = []
    for name in CSV_TABLES:
        path = DEMO_DATA_DIR / f"{name}.csv"
        if path.exists():
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{path.as_posix()}')")
        else:
            missing.append(path.name)

    policies_path = DEMO_DATA_DIR / "policies.json"
    if policies_path.exists():
        con.execute(f"CREATE VIEW policies AS SELECT * FROM read_json_auto('{policies_path.as_posix()}')")
    else:
        missing.append(policies_path.name)

    if missing:
        print(f"warning: missing demo-data files (run `python -m simulation.generate_all` first): {missing}")
    return con


def schema_summary(con: duckdb.DuckDBPyConnection) -> str:
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    lines = []
    for (table,) in tables:
        cols = con.execute(f"DESCRIBE {table}").fetchall()
        col_list = ", ".join(f"{c[0]} {c[1]}" for c in cols)
        lines.append(f"{table}({col_list})")
    return "\n".join(lines)


def ollama_generate(model: str, prompt: str) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_URL} ({e}). Is `ollama serve` running?"
        ) from e
    if "error" in data:
        raise RuntimeError(f"Ollama error from model '{model}': {data['error']}")
    return data["response"]


def extract_sql(text: str) -> str:
    if "```" in text:
        text = text.split("```")[1]
        if text.lower().startswith("sql"):
            text = text[3:]
    return text.strip().rstrip(";")


def ask(con: duckdb.DuckDBPyConnection, question: str) -> None:
    schema = schema_summary(con)
    sql_prompt = f"""You are a DuckDB SQL expert. Given this schema:

{schema}

Write a single DuckDB SQL query (output ONLY the SQL, no explanation, no markdown fences) that answers:
{question}
"""
    sql = extract_sql(ollama_generate(SQL_MODEL, sql_prompt))
    print(f"\n[SQL]\n{sql}\n")

    try:
        result = con.execute(sql).fetchdf()
    except duckdb.Error as e:
        print(f"Query failed: {e}")
        return

    print(result.head(20).to_string(index=False))

    answer_prompt = f"""Question: {question}

Query result (as a table, possibly truncated to 20 rows):
{result.head(20).to_string(index=False)}

Answer the question in 2-3 plain-English sentences based only on this result."""
    answer = ollama_generate(ANSWER_MODEL, answer_prompt)
    print(f"\n{answer.strip()}\n")


def main() -> None:
    con = connect()
    if len(sys.argv) > 1:
        ask(con, " ".join(sys.argv[1:]))
        return

    print("Offline chat over demo-data/ (models: SQL=%s, answer=%s). Ctrl+C or 'exit' to quit.\n"
          % (SQL_MODEL, ANSWER_MODEL))
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in ("exit", "quit"):
            break
        if not question:
            continue
        try:
            ask(con, question)
        except RuntimeError as e:
            print(f"error: {e}")


if __name__ == "__main__":
    main()
