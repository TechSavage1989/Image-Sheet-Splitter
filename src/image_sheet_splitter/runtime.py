import json
import os
import sys
from pathlib import Path


def parse_runtime_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    result = {
        "post_update_health": None,
        "post_update_from": None,
        "post_update_plan": None,
        "post_update_token": None,
        "rollback_message": None,
    }
    i = 0
    while i < len(argv):
        value = argv[i]
        if value == "--post-update-health" and i + 1 < len(argv):
            result["post_update_health"] = argv[i + 1]
            i += 2
            continue
        if value == "--post-update-from" and i + 1 < len(argv):
            result["post_update_from"] = argv[i + 1]
            i += 2
            continue
        if value == "--post-update-plan" and i + 1 < len(argv):
            result["post_update_plan"] = argv[i + 1]
            i += 2
            continue
        if value == "--post-update-rollback" and i + 1 < len(argv):
            result["rollback_message"] = argv[i + 1]
            i += 2
            continue
        if value == "--post-update-token" and i + 1 < len(argv):
            result["post_update_token"] = argv[i + 1]
            i += 2
            continue
        i += 1
    return result


def mark_healthy(path, version, token=None):
    if not path:
        return False
    target = Path(path)
    payload = {
        "pid": os.getpid(), "version": version, "status": "healthy",
        "token": token, "executable": str(Path(sys.executable).resolve()),
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp, target)
        return True
    except OSError:
        return False
