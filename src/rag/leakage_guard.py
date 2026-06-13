def validate_index_splits(splits):
    bad = [split for split in splits if split == "test" or split.endswith("-test")]
    if bad:
        raise ValueError(f"RAG index must not include test split labels: {bad}")


def exclude_same_id(item):
    return {str(item.get("id"))}
