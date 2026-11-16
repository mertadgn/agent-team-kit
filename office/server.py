"""Agent Ofisi — Claude Code oturumlarını tepeden gösteren yerel panel.

Çalıştır:  python server.py        ->  http://localhost:4747
Veri:      ~/.claude/projects/**/*.jsonl  (oturum kayıtları, alt agent'lar dahil)
           ./events.jsonl                 (hook.py'nin yazdığı canlı olaylar: izin bekliyor, bitti...)
Hiçbir şey dışarı gönderilmez; sadece bu bilgisayardaki dosyalar okunur.
"""
import collections, glob, http.server, json, os, pathlib, secrets, shutil, socketserver, subprocess, sys, threading, time
from datetime import datetime

HOME = pathlib.Path.home()
PROJECTS = HOME / ".claude" / "projects"
BASE = pathlib.Path(__file__).resolve().parent
EVENTS = BASE / "events.jsonl"


def team_dir():
    """Ekip klasörü: OFFICE_TEAM ortam değişkeni ya da ofis.json → {"team": "..."} (kurulum yazar)."""
    t = os.environ.get("OFFICE_TEAM")
    if not t:
        try:
            t = json.load(open(BASE / "ofis.json", encoding="utf-8-sig")).get("team")
        except Exception:
            t = None
    return pathlib.Path(t).expanduser() if t else None


TEAM = team_dir()
YONETIM = "Yönetim"


def placement(cwd):
    """cwd → (departman, çalışan). Ekip dışı → (None, None).
    <ekip>/<Departman>/<Çalışan>/…  (departman klasöründe DEPARTMAN.md var)  |  <ekip>/<Çalışan>/… → Yönetim"""
    if not TEAM or not cwd:
        return None, None
    try:
        rel = pathlib.Path(os.path.normcase(os.path.abspath(cwd))).relative_to(os.path.normcase(os.path.abspath(TEAM)))
    except ValueError:
        return None, None
    real = pathlib.Path(os.path.abspath(cwd)).parts[-len(rel.parts):] if rel.parts else ()
    if not real:
        return YONETIM, None
    if (TEAM / real[0] / "DEPARTMAN.md").exists():
        return real[0], (real[1] if len(real) > 1 else None)
    if not (TEAM / real[0]).exists():  # çalışan sonradan bir departmana taşınmışsa eski oturumları da oraya say
        for d in TEAM.iterdir():
            if (d / "DEPARTMAN.md").exists() and (d / real[0]).is_dir():
                return d.name, real[0]
    return YONETIM, real[0]
PORT = int(os.environ.get("OFFICE_PORT", "4747"))
WINDOW_H = float(os.environ.get("OFFICE_HOURS", "168"))  # bu kadar saat içinde dokunulan oturumlar gösterilir

# etkin token: önbellekten okuma ~0.1x, önbelleğe yazma ~2x, çıktı ~5x
W_IN, W_CW, W_CR, W_OUT = 1.0, 2.0, 0.1, 5.0

FRIENDLY_MCP = {"claude-in-chrome": "Chrome", "Claude_Browser": "Tarayıcı", "ccd_turn": "Uygulama",
                "ccd_session": "Oturumlar", "visualize": "Görselleştirme", "terminal": "Terminal"}


def iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def base(p):
    return os.path.basename(str(p).replace("\\", "/").rstrip("/")) or str(p)


def describe(name, inp):
    """Bir araç çağrısını insanca, kısa bir cümleye çevirir."""
    inp = inp or {}
    s = lambda v, n=70: (str(v).strip().replace("\n", " ")[: n - 1] + "…") if len(str(v)) > n else str(v).strip().replace("\n", " ")
    if name in ("Bash", "PowerShell"):
        return ("⌘", s(inp.get("description") or inp.get("command", "komut")))
    if name == "Read":
        return ("📖", "Okuyor: " + base(inp.get("file_path", "")))
    if name == "Write":
        return ("✍️", "Yazıyor: " + base(inp.get("file_path", "")))
    if name in ("Edit", "MultiEdit", "NotebookEdit"):
        return ("✏️", "Düzenliyor: " + base(inp.get("file_path", inp.get("notebook_path", ""))))
    if name in ("Glob", "Grep"):
        return ("🔎", "Arıyor: " + s(inp.get("pattern", ""), 50))
    if name == "WebSearch":
        return ("🌐", "Web'de arıyor: " + s(inp.get("query", ""), 50))
    if name == "WebFetch":
        u = str(inp.get("url", ""))
        return ("🌐", "Sayfa okuyor: " + (u.split("/")[2] if "//" in u else u))
    if name in ("Agent", "Task"):
        return ("👥", "Yardımcı görevlendirdi: " + s(inp.get("description", ""), 50))
    if name == "Skill":
        return ("📚", "Beceri yüklüyor: " + s(inp.get("skill", ""), 40))
    if name == "AskUserQuestion":
        return ("❓", "Sana soru soruyor")
    if name == "SendUserFile":
        return ("📎", "Sana dosya gönderiyor")
    if name == "Workflow":
        return ("🧩", "İş akışı çalıştırıyor")
    if name == "ToolSearch":
        return ("🧰", "Araç arıyor")
    if name == "mcp__ccd_turn__update_plan":
        return ("🗒️", "Görev listesini güncelliyor")
    if name == "mcp__ccd_turn__wrap_up":
        return ("✅", "İşi toparlıyor")
    if name.startswith("mcp__"):
        parts = name.split("__")
        srv = parts[1] if len(parts) > 1 else "bağlayıcı"
        srv = FRIENDLY_MCP.get(srv, srv if len(srv) < 24 else "Bağlayıcı")
        return ("🔌", f"{srv}: {parts[-1].replace('_', ' ')}")
    return ("🔧", name)


class Transcript:
    """Bir .jsonl oturum kaydını artımlı okur (sadece yeni eklenen satırlar)."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.usage = {}            # message id -> usage (son değer)
        self.usage_ts = {}         # message id -> zaman (limit tahmini için)
        self.tools = {}            # tool_use id -> (name, input, ts)
        self.done = set()          # sonucu gelmiş tool_use id'leri
        self.timeline = collections.deque(maxlen=40)
        self.first_prompt = None
        self.last_text = ""
        self.last_kind = None      # user | tool_result | tool_use | text
        self.last_ts = None
        self.first_ts = None
        self.model = None
        self.cwd = None
        self.session_id = None
        self.tool_counts = collections.Counter()
        self.agent_desc = None

    def refresh(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size < self.offset:  # dosya küçüldüyse baştan oku
            self.__init__(self.path)
        if size == self.offset:
            return
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        cut = data.rfind(b"\n")
        if cut < 0:
            return
        self.offset += cut + 1
        for line in data[: cut + 1].splitlines():
            try:
                self._line(json.loads(line))
            except Exception:
                pass

    def _line(self, r):
        t = r.get("type")
        ts = iso(r.get("timestamp", "")) if r.get("timestamp") else None
        if ts:
            self.last_ts = ts
            self.first_ts = self.first_ts or ts
        self.cwd = r.get("cwd") or self.cwd
        self.session_id = r.get("sessionId") or self.session_id
        self.entrypoint = r.get("entrypoint") or getattr(self, "entrypoint", None)
        m = r.get("message") or {}
        if t == "assistant":
            if m.get("model") and not str(m.get("model")).startswith("<"):
                self.model = m["model"]
            if m.get("usage") and m.get("id"):
                self.usage[m["id"]] = m["usage"]
                if ts:
                    self.usage_ts.setdefault(m["id"], ts)
            for c in m.get("content") or []:
                ct = c.get("type")
                if ct == "text" and c.get("text", "").strip():
                    self.last_text = c["text"].strip()
                    self.last_kind = "text"
                elif ct == "tool_use":
                    self.tools[c["id"]] = (c["name"], c.get("input") or {}, ts)
                    self.tool_counts[c["name"]] += 1
                    icon, txt = describe(c["name"], c.get("input"))
                    self.timeline.append({"t": ts, "icon": icon, "text": txt})
                    self.last_kind = "tool_use"
        elif t == "user":
            cont = m.get("content")
            if isinstance(cont, str):
                if self.first_prompt is None and r.get("origin", {}).get("kind", "human") == "human":
                    self.first_prompt = cont.strip()
                if not cont.startswith("<"):
                    self.timeline.append({"t": ts, "icon": "💬", "text": "Mesaj: " + cont.strip().replace("\n", " ")[:80]})
                self.last_kind = "user"
            elif isinstance(cont, list):
                for c in cont:
                    if c.get("type") == "tool_result":
                        self.done.add(c.get("tool_use_id"))
                        self.last_kind = "tool_result"
                    elif c.get("type") == "text":
                        txt = c.get("text", "")
                        if self.first_prompt is None and not txt.startswith("<"):
                            self.first_prompt = txt.strip()
                        self.last_kind = "user"

    # --- özetler ---
    def tokens(self):
        tot = collections.Counter()
        for u in self.usage.values():
            tot["input"] += u.get("input_tokens", 0) or 0
            tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
            tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            tot["output"] += u.get("output_tokens", 0) or 0
        eff = tot["input"] * W_IN + tot["cache_write"] * W_CW + tot["cache_read"] * W_CR + tot["output"] * W_OUT
        return {**tot, "effective": round(eff), "calls": len(self.usage)}

    def pending(self):
        return [(i, v) for i, v in self.tools.items() if i not in self.done]

    def status(self, now, mtime, hook_ev):
        age = now - (self.last_ts or mtime)
        pend = self.pending()
        # canlı hook olayı kayıttan daha yeniyse o kazanır
        if hook_ev and hook_ev["t"] >= (self.last_ts or 0) - 1:
            e = hook_ev["event"]
            if e == "SessionEnd":
                return "kapandi", "Oturum kapandı"
            if e == "Notification":
                msg = hook_ev.get("message") or "Onayını bekliyor"
                return "izin", msg[:90]
            if e == "Stop" and not pend:
                return "bekliyor", "Seni bekliyor"
        if pend and age < 900:
            name, inp, _ = pend[-1][1]
            if name == "AskUserQuestion":
                return "izin", "Sana soru sordu, cevabını bekliyor"
            icon, txt = describe(name, inp)
            return "calisiyor", f"{icon} {txt}"
        if self.last_kind in ("user", "tool_result") and age < 180:
            return "dusunuyor", "💭 Düşünüyor…"
        if age > 3600:
            return "bosta", "Boşta"
        if self.last_kind == "text":
            return "bekliyor", "Seni bekliyor"
        return "bosta", "Boşta"


CACHE = {}
LOCK = threading.Lock()


def tx(path):
    t = CACHE.get(path)
    if t is None:
        t = CACHE[path] = Transcript(path)
    t.refresh()
    return t


def read_title(session_dir):
    try:
        d = json.load(open(os.path.join(session_dir, "custom-title.json"), encoding="utf-8"))
        for v in d.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    except Exception:
        pass
    return None


def hook_events():
    """events.jsonl'in son satırları: session_id -> son olay; ayrıca alt agent başlangıçları."""
    last = {}
    if not EVENTS.exists():
        return last
    try:
        with open(EVENTS, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - 400_000))
            lines = f.read().splitlines()
            if n > 400_000:
                lines = lines[1:]  # ilk satır yarım olabilir
    except OSError:
        return last
    for l in lines:
        try:
            e = json.loads(l)
        except Exception:
            continue
        if e.get("event") in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SubagentStop"):
            # bunlar kayıttan da okunuyor; sadece "son olay" zamanını bozmasın diye durum olaylarını tutarız
            last.setdefault(e.get("session_id"), None)
            if e.get("event") == "UserPromptSubmit":
                last[e.get("session_id")] = e
            continue
        last[e.get("session_id")] = e
    return {k: v for k, v in last.items() if v}


def state():
    now = time.time()
    hooks = hook_events()
    panes = pane_map()
    hidden = hidden_ids()
    sessions = []
    tmap = {}
    with LOCK:
        for path in glob.glob(str(PROJECTS / "*" / "*.jsonl")):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if now - mtime > WINDOW_H * 3600:
                continue
            t = tx(path)
            if not t.usage and not t.first_prompt:
                continue
            sid = pathlib.Path(path).stem
            if sid in hidden:
                continue
            sdir = path[:-6]
            st, act = t.status(now, mtime, hooks.get(sid))
            helpers = []
            for sp in sorted(glob.glob(os.path.join(sdir, "**", "*.jsonl"), recursive=True)):
                try:
                    smt = os.path.getmtime(sp)
                except OSError:
                    continue
                s = tx(sp)
                sst, sact = s.status(now, smt, None)
                if sst == "bekliyor":  # bir alt agent'ın son metni = işi bitti
                    sst, sact = "bitti", "İşini bitirdi"
                helpers.append({
                    "id": pathlib.Path(sp).stem, "status": sst, "activity": sact,
                    "task": (s.first_prompt or "")[:160], "tokens": s.tokens(), "model": s.model,
                    "timeline": list(s.timeline)[-12:], "last_ts": s.last_ts or smt,
                    "summary": s.last_text[:400],
                })
            tk = t.tokens()
            tmap[sid] = t
            sessions.append({
                "id": sid, "title": read_title(sdir) or (t.first_prompt or "Adsız oturum").replace("\n", " ")[:70],
                "project": base(t.cwd) if t.cwd else pathlib.Path(path).parent.name,
                "dept": placement(t.cwd)[0], "worker": placement(t.cwd)[1],
                "cwd": t.cwd, "model": t.model, "status": st, "activity": act,
                "last_text": t.last_text[:500], "tokens": tk,
                "tokens_all": tk["effective"] + sum(h["tokens"]["effective"] for h in helpers),
                "timeline": list(t.timeline)[-20:], "helpers": helpers,
                "started": t.first_ts, "last_ts": t.last_ts or mtime,
                "top_tools": t.tool_counts.most_common(6),
                "control": control_for(sid, getattr(t, "entrypoint", None), panes),
                "entrypoint": getattr(t, "entrypoint", None),
            })
    # Devam ettirilen (resume) konuşmalar: Claude Code eski konuşmayı yeni bir oturum dosyasına kopyalar.
    # Bir oturumun bütün mesajları daha büyük başka bir oturumda da varsa o eskisidir: gizlenir, tokenleri iki kez sayılmaz.
    ids = {sid: set(t.usage) for sid, t in tmap.items()}
    eski = set()
    for a_id, ia in ids.items():
        if ia and any(b != a_id and len(ib) > len(ia) and ia <= ib for b, ib in ids.items()):
            eski.add(a_id)
    # hiç cevap üretmemiş (boşa açılıp kapanmış) ve 10 dakikadan eski oturumlar da masa sayılmaz
    sessions = [x for x in sessions if x["id"] not in eski
                and not (x["tokens"]["calls"] == 0 and now - x["last_ts"] > 600)]
    order = {"izin": 0, "calisiyor": 1, "dusunuyor": 2, "bekliyor": 3, "bosta": 4, "kapandi": 5}
    sessions.sort(key=lambda s: (order.get(s["status"], 9), -s["last_ts"]))
    with LOCK:
        lim = limits(now)
    depts = []
    if TEAM and TEAM.exists():
        depts = sorted(d.name for d in TEAM.iterdir() if (d / "DEPARTMAN.md").exists())
    return {"now": now, "window_h": WINDOW_H, "hooks": EVENTS.exists(), "sessions": sessions, "limits": lim,
            "team": str(TEAM) if TEAM else None, "depts": depts, "roster": roster(sessions),
            "archive": archive_list(), "hidden": len(hidden)}


def _commands(folder):
    sk = folder / ".claude" / "skills"
    try:
        return sorted("/" + d.name for d in sk.iterdir() if (d / "SKILL.md").exists())
    except OSError:
        return []


def roster(sessions):
    """Ekipteki bütün çalışanlar (oturumu açık olsun olmasın): departman, ad, klasör, komutlar, son görülme."""
    if not TEAM or not TEAM.exists():
        return []
    seen = {}
    for x in sessions:  # son WINDOW_H saatteki oturumlardan son görülme zamanı
        k = (x.get("dept"), x.get("worker"))
        if k[1]:
            seen[k] = max(seen.get(k, 0), x["last_ts"])
    out = []
    try:
        top = sorted(TEAM.iterdir(), key=lambda d: d.name.lower())
    except OSError:
        return []
    for d in top:
        if not d.is_dir():
            continue
        if (d / "DEPARTMAN.md").exists():
            for w in sorted(d.iterdir(), key=lambda x: x.name.lower()):
                if w.is_dir() and (w / "CLAUDE.md").exists():
                    out.append({"dept": d.name, "worker": w.name, "path": str(w), "commands": _commands(w),
                                "last_ts": seen.get((d.name, w.name)), "chief": w.name.endswith("Şefi")})
        elif (d / "CLAUDE.md").exists():
            out.append({"dept": YONETIM, "worker": d.name, "path": str(d), "commands": _commands(d),
                        "last_ts": seen.get((YONETIM, d.name)), "chief": False})
    return out


USAGE = BASE / "usage.json"  # Claude'un uygulamadan okuyup yazdığı kesin limit ölçümü


def eff(u):
    return ((u.get("input_tokens", 0) or 0) * W_IN + (u.get("cache_creation_input_tokens", 0) or 0) * W_CW
            + (u.get("cache_read_input_tokens", 0) or 0) * W_CR + (u.get("output_tokens", 0) or 0) * W_OUT)


def spent(a, b):
    """[a, b] zaman aralığında tüm oturumlarda (alt agent'lar dahil) harcanan etkin token."""
    tot = 0.0
    for t in list(CACHE.values()):
        for mid, ts in t.usage_ts.items():
            if a <= ts <= b:
                tot += eff(t.usage[mid])
    return tot


def limits(now):
    """Son kesin ölçüm + o andan beri harcanan tokena göre canlı tahmin."""
    try:
        snap = json.load(open(USAGE, encoding="utf-8"))
    except Exception:
        return None
    t0 = snap.get("t", now)
    out = []
    for w in snap.get("windows", []):
        reset = iso(w.get("resetsAt", "")) or now
        length = 5 * 3600 if "5" in w.get("label", "")[:3] else 7 * 86400
        start = reset - length
        p0 = float(w.get("percentUsed", 0))
        rate = p0 / spent(start, t0) if p0 > 0 and spent(start, t0) > 0 else None  # yüzde / etkin token
        est, reset_now, rolled = p0, reset, False
        if now > reset:  # pencere yenilendi: yeni pencerede baştan say
            rolled = True
            while reset_now < now:
                reset_now += length
            est = rate * spent(reset_now - length, now) if rate else 0.0
        elif rate:
            est = p0 + rate * spent(t0, now)
        out.append({"label": w.get("label"), "snapshot": p0, "estimate": round(min(est, 100), 1),
                    "estimated": bool(rate) and (now - t0 > 60 or rolled), "resets_at": reset_now, "rolled": rolled})
    return {"t": t0, "plan": snap.get("plan"), "windows": out}


# --- Panodan oturuma mesaj (tmux) ---------------------------------------------------------------------------
# Terminalde tmux içinde açılmış bir Claude Code oturumuna panodan mesaj yazılır ya da Esc ile durdurulur.
# Oturum ↔ panel eşleşmesi hook.py'nin SessionStart kaydından gelir (TMUX_PANE). Güvenlik: sadece 127.0.0.1,
# Host/Origin kontrolü ve her açılışta değişen, sadece panonun kendi sayfasına gömülen bir anahtar.
TOKEN = secrets.token_urlsafe(24)
PANE_CACHE = {}  # (socket, pane) -> (zaman, komut ya da None)


def tmux(socket, *args):
    cmd = ["tmux"] + (["-S", socket] if socket else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5)


def pane_command(socket, pane):
    """Paneldeki programın adı (claude/node), panel yoksa None. 5 sn önbellekli."""
    key = (socket, pane)
    hit = PANE_CACHE.get(key)
    if hit and time.time() - hit[0] < 5:
        return hit[1]
    cur = None
    if shutil.which("tmux"):
        try:
            r = tmux(socket, "display-message", "-p", "-t", pane, "#{pane_current_command}")
            cur = r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            cur = None
    PANE_CACHE[key] = (time.time(), cur)
    return cur


def pane_map():
    """session_id -> {pane, socket}. Bir panel en son orada başlayan oturuma aittir; kapanan oturumların paneli düşer."""
    if not EVENTS.exists():
        return {}
    starts, owner, ended = {}, {}, set()
    try:
        lines = EVENTS.read_bytes().splitlines()[-20000:]
    except OSError:
        return {}
    for l in lines:
        try:
            e = json.loads(l)
        except Exception:
            continue
        sid = e.get("session_id")
        if e.get("event") == "SessionStart" and e.get("tmux_pane"):
            k = (e.get("tmux_socket"), e["tmux_pane"])
            starts[sid] = {"pane": e["tmux_pane"], "socket": e.get("tmux_socket")}
            owner[k] = sid
            ended.discard(sid)
        elif e.get("event") == "SessionEnd":
            ended.add(sid)
    return {sid: v for sid, v in starts.items() if sid not in ended and owner.get((v["socket"], v["pane"])) == sid}


def control_for(sid, entrypoint, panes):
    if entrypoint and "desktop" in entrypoint:
        return {"ok": False, "why": "Bu oturum Claude masaüstü uygulamasında açık. Mesajı uygulamadan gönder."}
    p = panes.get(sid)
    if not p:
        return {"ok": False, "why": "Bu oturum tmux içinde açılmamış. Mesaj gönderebilmek için oturumu `ekip <çalışan>` ile ya da tmux içinde `claude` ile aç."}
    cur = pane_command(p["socket"], p["pane"])
    if cur is None:
        return {"ok": False, "why": "Oturumun tmux paneli artık yok (terminal kapanmış olabilir)."}
    if not any(x in cur for x in ("claude", "node")):
        return {"ok": False, "why": f"Panelde şu an Claude Code değil `{cur}` çalışıyor."}
    return {"ok": True, "pane": p["pane"]}


def deliver(sid, text=None, action=None):
    p = pane_map().get(sid)
    if not p:
        return False, "Bu oturumun tmux paneli bilinmiyor."
    PANE_CACHE.pop((p["socket"], p["pane"]), None)
    cur = pane_command(p["socket"], p["pane"])
    if not cur or not any(x in cur for x in ("claude", "node")):
        return False, "Panelde Claude Code çalışmıyor."
    if action == "interrupt":
        r = tmux(p["socket"], "send-keys", "-t", p["pane"], "Escape")
        return r.returncode == 0, r.stderr.strip() or "Durdurma (Esc) gönderildi."
    if action == "close":  # o anki işi durdur, sonra /exit: Claude Code kapanır, SessionEnd hook'u "kapandı" yazar
        tmux(p["socket"], "send-keys", "-t", p["pane"], "Escape")
        time.sleep(0.4)
        r1 = tmux(p["socket"], "send-keys", "-t", p["pane"], "-l", "/exit")
        time.sleep(0.2)
        r2 = tmux(p["socket"], "send-keys", "-t", p["pane"], "Enter")
        ok = r1.returncode == 0 and r2.returncode == 0
        return ok, "Mesai bitiriliyor (/exit gönderildi)." if ok else (r1.stderr or r2.stderr).strip()
    text = (text or "").strip()
    if not text:
        return False, "Mesaj boş."
    if len(text) > 8000:
        return False, "Mesaj çok uzun (en fazla 8000 karakter)."
    # köşeli parantezli yapıştırma: çok satırlı mesaj tek parça gider, satır sonları gönderme sayılmaz
    r1 = tmux(p["socket"], "set-buffer", "-b", "agentofisi", "--", text)
    r2 = tmux(p["socket"], "paste-buffer", "-p", "-d", "-b", "agentofisi", "-t", p["pane"])
    time.sleep(0.15)
    r3 = tmux(p["socket"], "send-keys", "-t", p["pane"], "Enter")
    ok = all(r.returncode == 0 for r in (r1, r2, r3))
    return ok, "Mesaj gönderildi." if ok else (r1.stderr or r2.stderr or r3.stderr).strip()


# --- Masadan kaldır (gizle) ve işten çıkar (arşive taşı) ---------------------------------------------------------
HIDDEN = BASE / "gizli-masalar.json"
ARSIV = "_Arşiv"


def hidden_ids():
    try:
        return set(json.load(open(HIDDEN, encoding="utf-8-sig")))
    except Exception:
        return set()


def set_hidden(sid, hide):
    ids = hidden_ids()
    (ids.add if hide else ids.discard)(sid)
    tmp = HIDDEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    os.replace(tmp, HIDDEN)


def worker_dir(dept, worker):
    """Ekip klasörü içinde gerçek bir çalışan klasörü mü? Değilse None (yol kaçırma denemelerine karşı)."""
    if not TEAM or not worker or "/" in worker or "\\" in worker or worker.startswith((".", "_")):
        return None
    if dept and dept != YONETIM and ("/" in dept or "\\" in dept or dept.startswith((".", "_"))):
        return None
    d = (TEAM / worker) if (not dept or dept == YONETIM) else (TEAM / dept / worker)
    try:
        d.resolve().relative_to(TEAM.resolve())
    except ValueError:
        return None
    return d if (d / "CLAUDE.md").exists() else None


def _drop_rows(md, worker):
    """Markdown tablolarından ilk hücresi bu çalışan olan satırları çıkar; geri alma için (satır no, satır) döndür."""
    if not md.exists():
        return []
    lines = md.read_text(encoding="utf-8").split("\n")
    keep, gone = [], []
    for i, l in enumerate(lines):
        cells = [c.strip() for c in l.strip().strip("|").split("|")] if l.lstrip().startswith("|") else []
        if cells and cells[0] == worker:
            gone.append([i, l])
        else:
            keep.append(l)
    if gone:
        md.write_text("\n".join(keep), encoding="utf-8")
    return gone


def archive_list():
    out = []
    a = TEAM / ARSIV if TEAM else None
    if a and a.exists():
        for d in sorted(a.iterdir()):
            try:
                meta = json.load(open(d / ".arsiv.json", encoding="utf-8"))
                out.append({"id": d.name, "dept": meta.get("dept"), "worker": meta.get("worker"), "t": meta.get("t")})
            except Exception:
                pass
    return out


def fire(dept, worker, sessions):
    d = worker_dir(dept, worker)
    if not d:
        return False, "Böyle bir çalışan bulunamadı."
    if worker == "Worker Kurucu":
        return False, "Worker Kurucu işten çıkarılamaz (yeni çalışanları o kuruyor)."
    busy = [x for x in sessions if x.get("dept") == (dept or YONETIM) and x.get("worker") == worker
            and x["status"] != "kapandi" and time.time() - x.get("last_ts", 0) < 6 * 3600]  # seni bekleyen de mesaide sayılır
    if busy:
        return False, "Bu çalışan şu an mesaide. Önce mesaisini bitir."
    a = TEAM / ARSIV
    a.mkdir(exist_ok=True)
    name = f"{(dept or YONETIM)} - {worker} - {time.strftime('%Y-%m-%d %H%M')}"
    dst = a / name
    try:
        shutil.move(str(d), str(dst))
    except OSError as e:
        return False, f"Klasör taşınamadı: açık bir oturum ya da program klasörü kullanıyor olabilir ({e.strerror or e})."
    rows = {}
    for md in ([TEAM / dept / "DEPARTMAN.md"] if dept and dept != YONETIM else []) + [TEAM / "EKIP.md"]:
        g = _drop_rows(md, worker)
        if g:
            rows[str(md.relative_to(TEAM))] = g
    (dst / ".arsiv.json").write_text(json.dumps({"dept": dept or YONETIM, "worker": worker, "from": str(d),
                                                 "t": time.time(), "rows": rows}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return True, f"{worker} arşive taşındı. Arşivden geri alabilirsin."


def rehire(aid):
    if not TEAM or not aid or "/" in aid or "\\" in aid or aid.startswith("."):
        return False, "Geçersiz arşiv kaydı."
    src = TEAM / ARSIV / aid
    try:
        meta = json.load(open(src / ".arsiv.json", encoding="utf-8"))
    except Exception:
        return False, "Arşiv kaydı okunamadı."
    dst = pathlib.Path(meta["from"])
    try:
        dst.resolve().relative_to(TEAM.resolve())
    except ValueError:
        return False, "Arşiv kaydı ekip klasörünün dışını gösteriyor."
    if dst.exists():
        return False, f"{dst.name} adında bir klasör zaten var."
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
    except OSError as e:
        return False, f"Klasör taşınamadı ({e.strerror or e})."
    for rel, gone in (meta.get("rows") or {}).items():  # tablo satırlarını eski yerlerine koy
        md = TEAM / rel
        if md.exists():
            lines = md.read_text(encoding="utf-8").split("\n")
            for i, l in sorted(gone):
                lines.insert(min(i, len(lines)), l)
            md.write_text("\n".join(lines), encoding="utf-8")
    try:
        (dst / ".arsiv.json").unlink()
    except OSError:
        pass
    return True, f"{meta.get('worker')} geri işe alındı."


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(BASE), **k)

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _local(self):
        """DNS rebinding ve başka sitelerden gelen istekleri reddet."""
        host = (self.headers.get("Host") or "").lower()
        ok_hosts = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
        origin = self.headers.get("Origin")
        return host in ok_hosts and (origin is None or origin.lower() in {f"http://{h}" for h in ok_hosts})

    def do_GET(self):
        if not self._local():
            return self._json(403, {"error": "yalnızca localhost"})
        if self.path.startswith("/api/state"):
            return self._json(200, state())
        if self.path in ("/", "", "/index.html"):
            body = (BASE / "index.html").read_text(encoding="utf-8").replace("{{OFFICE_TOKEN}}", TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return self._json(404, {"error": "yok"})  # pano klasöründeki başka dosyalar (events.jsonl vb.) sunulmaz

    def do_POST(self):
        if not self._local() or self.headers.get("X-Office-Token") != TOKEN:
            return self._json(403, {"ok": False, "message": "izin yok (sayfayı yenile)"})
        if self.path not in ("/api/send", "/api/desk", "/api/worker"):
            return self._json(404, {"ok": False, "message": "yok"})
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 64_000)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._json(400, {"ok": False, "message": "geçersiz istek"})
        act = req.get("action")
        if self.path == "/api/send":
            ok, msg = deliver(str(req.get("id", "")), req.get("text"), act)
        elif self.path == "/api/desk":  # masadan kaldır / geri getir
            if act not in ("hide", "unhide-all"):
                return self._json(400, {"ok": False, "message": "geçersiz işlem"})
            if act == "hide":
                set_hidden(str(req.get("id", "")), True)
                ok, msg = True, "Masa panodan kaldırıldı."
            else:
                tmp = HIDDEN.with_suffix(".tmp"); tmp.write_text("[]", encoding="utf-8"); os.replace(tmp, HIDDEN)
                ok, msg = True, "Kaldırılan bütün masalar geri getirildi."
        else:  # /api/worker: işten çıkar (arşive taşı) / geri al
            if act == "fire":  # state() kendi kilidini alır; burada ayrıca kilit alınmaz (kilitlenme olur)
                ok, msg = fire(str(req.get("dept") or ""), str(req.get("worker") or ""), state()["sessions"])
            elif act == "rehire":
                ok, msg = rehire(str(req.get("id") or ""))
            else:
                return self._json(400, {"ok": False, "message": "geçersiz işlem"})
        return self._json(200 if ok else 409, {"ok": ok, "message": msg})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"Agent Ofisi: http://localhost:{PORT}  (son {WINDOW_H:g} saat)", flush=True)
    Server(("127.0.0.1", PORT), H).serve_forever()
