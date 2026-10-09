"""Read the actual loaded Paddle recognizer dictionary without language guesses."""

from __future__ import annotations


def model_characters(engine):
    seen = set()

    def walk(obj, depth=0):
        if obj is None or id(obj) in seen or depth > 8:
            return set()
        seen.add(id(obj))
        fields = getattr(obj, "__dict__", {})
        for name in ("character", "character_list", "characters"):
            value = fields.get(name)
            if isinstance(value, (list, tuple)) and value:
                return set("".join(str(char) for char in value))
        children = list(fields.get("_pipelines") or [])
        for name in ("paddlex_pipeline", "_pipeline", "paddlex_predictor", "_predictor", "predictor",
                     "text_rec_model", "post_op", "postprocess_op"):
            if fields.get(name) is not None:
                children.append(fields[name])
        for child in children:
            found = walk(child, depth + 1)
            if found:
                return found
        return set()

    return walk(engine)
