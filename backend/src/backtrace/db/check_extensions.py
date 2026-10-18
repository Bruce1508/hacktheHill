import argparse

from sqlalchemy import create_engine, text

CHECKED_EXTENSIONS = ["timescaledb", "vector", "vectorscale", "pg_textsearch"]


def check_extensions(database_url: str) -> dict[str, bool]:
    engine = create_engine(database_url)
    results: dict[str, bool] = {}
    with engine.connect() as conn:
        available = {
            row[0]
            for row in conn.execute(text("SELECT name FROM pg_available_extensions"))
        }
        installed = {
            row[0] for row in conn.execute(text("SELECT extname FROM pg_extension"))
        }
        for ext in CHECKED_EXTENSIONS:
            results[ext] = ext in available or ext in installed
    engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    results = check_extensions(args.database_url)
    for ext, available in results.items():
        print(f"{ext}: {'available' if available else 'NOT available'}")


if __name__ == "__main__":
    main()
