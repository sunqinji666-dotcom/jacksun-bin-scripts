#!/usr/bin/env python3
"""启动 Claude Code 前，把指定目录标记为「已信任」，免掉每次的信任确认弹窗。

用法: trust-cwd.py [目录]   (默认取当前工作目录)

实现要点:
- 写入 ~/.claude.json 的 projects[<目录>].hasTrustDialogAccepted = true
- 用 flock 串行化，避免多个 claude 同时启动时互相覆盖
- 临时文件 + os.replace 原子替换，保留 600 权限
- 任何异常都吞掉并返回 0，绝不能挡住宿主命令的启动
"""
import fcntl
import json
import os
import sys
import tempfile


def mark_trusted(target: str) -> bool:
    cfg = os.path.expanduser("~/.claude.json")
    if not os.path.isfile(cfg):
        return False

    with open(cfg + ".trust.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(cfg, encoding="utf-8") as f:
            data = json.load(f)
        projects = data.setdefault("projects", {})
        entry = projects.setdefault(target, {})
        if entry.get("hasTrustDialogAccepted") is True:
            return False  # 已经是信任状态，不用写盘
        entry["hasTrustDialogAccepted"] = True

        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cfg), prefix=".claude.json.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, cfg)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return True


def main() -> None:
    target = os.path.realpath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    if mark_trusted(target):
        print(f"claude-trust: 已标记 {target}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - 绝不阻挡启动
        print(f"claude-trust: skipped ({exc})", file=sys.stderr)
    sys.exit(0)
