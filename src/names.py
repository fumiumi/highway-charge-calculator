"""Name equality only; no transliteration guessing or physical-node merging."""
import re
import unicodedata


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).casefold()
    for old, new in (("インターチェンジ", "ic"), ("ジャンクション", "jct"),
                     ("interchange", "ic"), ("junction", "jct")):
        name = name.replace(old, new)
    return re.sub(r"\s+", "", name)


def name_keys(name: str) -> set[str]:
    key = normalize_name(name)
    return {key, re.sub(r"(?:ic|jct)$", "", key)}


def node_matches(node, name: str) -> bool:
    key = normalize_name(name)
    if key.endswith("ic") and node.node_type == "JCT":
        return False
    if key.endswith("jct") and node.node_type != "JCT":
        return False
    return any(name_keys(name) & name_keys(a) for a in [node.name, *node.aliases] if a)
