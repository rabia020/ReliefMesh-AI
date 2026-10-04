import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.embeddings import embed_texts


def main() -> None:
    vectors = embed_texts(["boat needed", "need a boat"])
    print("Embedding model ready:", len(vectors), "vectors of size", len(vectors[0]))


if __name__ == "__main__":
    main()