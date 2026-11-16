"""Claude Code hook'u: olayı events.jsonl'e bir satır olarak yazar. Hiçbir zaman Claude'u durdurmaz (her durumda exit 0).

SessionStart olayında oturumun tmux paneli de kaydedilir (TMUX_PANE). Agent Ofisi panodan mesaj gönderirken bunu kullanır.
"""
import json, os, sys, time

try:
    d = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.jsonl")
    e = {"t": time.time(), "event": d.get("hook_event_name"), "session_id": d.get("session_id"),
         "cwd": d.get("cwd"), "tool": d.get("tool_name"), "message": d.get("message")}
    if e["event"] == "SessionStart":
        e["source"] = d.get("source")
        if os.environ.get("TMUX_PANE"):
            e["tmux_pane"] = os.environ["TMUX_PANE"]
            e["tmux_socket"] = (os.environ.get("TMUX") or "").split(",")[0] or None
    if os.path.exists(p) and os.path.getsize(p) > 5_000_000:  # 5 MB'ı geçince son yarısını tut
        with open(p, "rb") as f:
            f.seek(-2_500_000, 2)
            keep = f.read().split(b"\n", 1)[-1]
        with open(p, "wb") as f:
            f.write(keep)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
except Exception:
    pass
sys.exit(0)
