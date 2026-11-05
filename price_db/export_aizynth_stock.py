"""Export the offline Enamine catalog as an AiZynthFinder InChIKey stock."""

from contextlib import closing
from pathlib import Path
import sqlite3


HERE = Path(__file__).resolve().parent


def export(db_path=HERE / "catalog.sqlite", output=HERE / "enamine_inchikeys.txt"):
    temporary = output.with_suffix(".building.txt")
    n = 0
    with closing(sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)) as db, temporary.open("w", encoding="ascii") as file:
        for (key,) in db.execute("SELECT DISTINCT inchikey FROM stock ORDER BY inchikey"):
            file.write(key + "\n")
            n += 1
    temporary.replace(output)
    print(f"Exported {n} distinct exact InChIKeys to {output}")


if __name__ == "__main__":
    export()
