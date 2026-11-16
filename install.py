#!/usr/bin/env python3
"""Agent Ekip Kiti kurulumu — Windows, macOS ve Linux.

    python install.py --name "Ayşe"                       # varsayılanlarla kur
    python install.py --name "Ayşe" --team ~/AgentTeam --office ~/AgentTeam/"Agent Ofisi"
    python install.py --check                              # kurulumu kontrol et
    python install.py --uninstall                          # hook'ları ayarlardan kaldır (dosyalara dokunmaz)

Ne yapar:
  1. Ekip klasörünü kurar: ORTAK.md (ortak kurallar), EKIP.md (ekip listesi), Worker Kurucu/ (çalışan kuran çalışan)
  2. Agent Ofisi'ni kurar: server.py + index.html + hook.py + başlatma betiği
  3. ~/.claude/settings.json'a 4 küçük hook ekler (önce yedek alır; var olan ayarlara dokunmaz)
Var olan dosyaların üzerine yazmaz (--force ile yedek alıp yazar). Tekrar çalıştırmak güvenlidir.
Sadece Python standart kütüphanesi kullanılır; internet gerekmez.
"""
import argparse, datetime, getpass, json, os, pathlib, shutil, stat, subprocess, sys

KIT = pathlib.Path(__file__).resolve().parent
HOOK_EVENTS = ["SessionStart", "Notification", "Stop", "UserPromptSubmit", "SessionEnd"]
MARKER = "--agent-office"
TODAY = datetime.date.today().isoformat()
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def say(icon, msg):
    print(f"  {icon} {msg}")


def posix(p):
    return str(p).replace("\\", "/")


def render(src, dst, values, force):
    if dst.exists() and not force:
        say("=", f"zaten var, dokunulmadı: {dst}")
        return
    if dst.exists():
        shutil.copy2(dst, dst.with_name(dst.name + f".yedek-{STAMP}"))
    text = src.read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    say("+", f"yazıldı: {dst}")


def copytree(src, dst, force):
    if dst.exists() and not force:
        say("=", f"zaten var, dokunulmadı: {dst}")
        return
    if dst.exists():
        bak = dst.with_name(dst.name + f".yedek-{STAMP}")
        shutil.move(str(dst), str(bak))
        say("~", f"eski klasör yedeklendi: {bak}")
    shutil.copytree(src, dst)
    say("+", f"kopyalandı: {dst}")


def load_settings(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        sys.exit(f"HATA: {path} geçerli bir JSON değil ({e}). Düzeltip tekrar dene; dosyaya dokunulmadı.")


def save_settings(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + f".yedek-{STAMP}"))
        say("~", f"ayar yedeği: {path.name}.yedek-{STAMP}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def is_ours(h):
    c = str(h.get("command", "")).replace("\\", "/")
    return MARKER in c or c.rstrip().rstrip('"').endswith("agent-office/hook.py")  # eski elle kurulumlar da


def strip_ours(settings):
    """Bizim hook kayıtlarımızı (MARKER içerenler) ayarlardan çıkarır; başkalarına dokunmaz."""
    hooks = settings.get("hooks") or {}
    removed = 0
    for ev in list(hooks):
        groups = []
        for g in hooks[ev] or []:
            hs = [h for h in g.get("hooks", []) if not is_ours(h)]
            removed += len(g.get("hooks", [])) - len(hs)
            if hs:
                groups.append({**g, "hooks": hs})
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    return removed


def install_hooks(settings_path, office):
    s = load_settings(settings_path)
    strip_ours(s)  # eski kayıtları temizle (yol değişmiş olabilir)
    cmd = f'"{posix(sys.executable)}" "{posix(office / "hook.py")}" {MARKER}'
    hooks = s.setdefault("hooks", {})
    for ev in HOOK_EVENTS:
        hooks.setdefault(ev, []).append({"hooks": [{"type": "command", "command": cmd, "timeout": 5}]})
    save_settings(settings_path, s)
    say("+", f"hook'lar eklendi ({', '.join(HOOK_EVENTS)}): {settings_path}")


def write_launchers(office, port):
    py = str(sys.executable)
    bat = office / "baslat.bat"
    bat.write_text(f'@echo off\r\nrem Agent Ofisi\r\ncd /d "%~dp0"\r\nset OFFICE_PORT={port}\r\n'
                   f'start "" http://localhost:{port}\r\n"{py}" server.py\r\n', encoding="utf-8")
    sh = office / "baslat.sh"
    sh.write_text(f'#!/bin/sh\n# Agent Ofisi\ncd "$(dirname "$0")"\nexport OFFICE_PORT={port}\n'
                  f'URL=http://localhost:{port}\n'
                  f'# tarayıcıyı aç (macOS: open, Linux: xdg-open; Ubuntu\'daki "open" komutu openvt\'dir, kullanılmaz)\n'
                  f'( sleep 1; if [ "$(uname)" = "Darwin" ]; then open "$URL"; '
                  f'elif command -v xdg-open >/dev/null; then xdg-open "$URL"; fi ) >/dev/null 2>&1 &\n'
                  f'exec "{posix(py)}" server.py\n', encoding="utf-8")
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    say("+", f"başlatma betikleri: {bat.name}, {sh.name}")


LAUNCHER = r"""#!/bin/sh
# ekip — bir çalışanı tmux içinde açar; böylece Agent Ofisi'nden ona mesaj gönderilebilir.
#   ekip                      çalışanları listele
#   ekip "Worker Kurucu"      çalışanı aç (zaten açıksa o tmux oturumuna bağlan)
#   ekip "Worker Kurucu" "/yeni-calisan bana ... aç"   ilk mesajla aç
TEAM="__TEAM__"
if [ -z "$1" ]; then
  echo "Ekip ($TEAM):"
  for d in "$TEAM"/*/; do
    if [ -f "$d/CLAUDE.md" ]; then echo "  $(basename "$d")"
    elif [ -f "$d/DEPARTMAN.md" ]; then
      for w in "$d"*/; do [ -f "$w/CLAUDE.md" ] && echo "  $(basename "$d")/$(basename "$w")"; done
    fi
  done
  echo; echo "Kullanım: ekip \"<Departman>/<Çalışan>\" [ilk mesaj]   (departmansız çalışan: ekip \"<Çalışan>\")"; exit 0
fi
DIR="$TEAM/$1"; shift
[ -d "$DIR" ] || { echo "Böyle bir çalışan yok: $DIR"; exit 1; }
command -v claude >/dev/null || { echo "claude komutu bulunamadı (Claude Code kurulu mu?)"; exit 1; }
if ! command -v tmux >/dev/null; then
  echo "tmux kurulu değil: panodan mesaj gönderme çalışmaz. Kurmak için: sudo apt install tmux"
  cd "$DIR" && exec claude "$@"
fi
NAME=$(basename "$DIR" | tr ' ' '-' | tr -cd 'A-Za-z0-9_-'); [ -n "$NAME" ] || NAME=calisan
if [ -n "$TMUX" ]; then
  exec tmux new-window -n "$NAME" -c "$DIR" claude "$@"
elif tmux has-session -t "=$NAME" 2>/dev/null; then
  exec tmux attach -t "=$NAME"
else
  exec tmux new-session -s "$NAME" -c "$DIR" claude "$@"
fi
"""


def write_ekip(team):
    """Linux/macOS: ~/.local/bin/ekip başlatıcısı (Windows'ta tmux yok, atlanır)."""
    if os.name == "nt":
        say("=", "ekip komutu atlandı (Windows'ta tmux yok; panodan mesaj gönderme WSL/Linux/macOS'ta çalışır)")
        return
    b = pathlib.Path.home() / ".local" / "bin"
    b.mkdir(parents=True, exist_ok=True)
    f = b / "ekip"
    f.write_text(LAUNCHER.replace("__TEAM__", posix(team)), encoding="utf-8")
    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    say("+", f"ekip komutu: {f}")
    if str(b) not in os.environ.get("PATH", "").split(os.pathsep):
        say("!", f"{b} PATH'te değil. Yeni bir terminal aç ya da ~/.profile'a ekle: export PATH=\"$HOME/.local/bin:$PATH\"")
    if not shutil.which("tmux"):
        say("!", "tmux kurulu değil. Panodan mesaj gönderebilmek için: sudo apt install tmux (macOS: brew install tmux)")


def check(team, office, settings_path):
    ok = True
    print("\nKontrol:")
    v = sys.version_info
    say("✓" if v >= (3, 9) else "✗", f"Python {v.major}.{v.minor} ({sys.executable})")
    ok &= v >= (3, 9)
    claude = shutil.which("claude")
    if claude:
        try:
            ver = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            ver = "sürüm okunamadı"
        say("✓", f"Claude Code: {ver}")
    else:
        say("!", "Claude Code (claude) PATH'te bulunamadı. Masaüstü uygulamasını kullanıyorsan sorun değil.")
    for p in [team / "ORTAK.md", team / "EKIP.md", team / "Worker Kurucu" / "CLAUDE.md",
              team / "Worker Kurucu" / ".claude" / "skills" / "yeni-calisan" / "SKILL.md",
              office / "server.py", office / "index.html", office / "hook.py"]:
        e = p.exists()
        ok &= e
        say("✓" if e else "✗", posix(p))
    left = [p for p in [team / "ORTAK.md", team / "EKIP.md"] if p.exists() and "{{" in p.read_text(encoding="utf-8")]
    for p in left:
        say("!", f"doldurulmamış yer tutucu var: {p}")
    s = load_settings(settings_path)
    ours = [ev for ev, gs in (s.get("hooks") or {}).items() for g in gs for h in g.get("hooks", [])
            if MARKER in str(h.get("command", ""))]
    say("✓" if set(HOOK_EVENTS) <= set(ours) else "!", f"hook'lar: {', '.join(sorted(set(ours))) or 'yok'} ({settings_path})")
    try:
        sys.path.insert(0, str(office))
        import importlib
        srv = importlib.import_module("server")
        st = srv.state()
        say("✓", f"Agent Ofisi veri okuyucu çalışıyor: {len(st['sessions'])} oturum görünüyor")
    except Exception as e:
        ok = False
        say("✗", f"Agent Ofisi veri okuyucu hata verdi: {e}")
    print("\nSonuç:", "HAZIR" if ok else "EKSİKLER VAR (yukarıdaki ✗ satırları)")
    return ok


def main():
    home = pathlib.Path.home()
    ap = argparse.ArgumentParser(description="Agent Ekip Kiti kurulumu")
    ap.add_argument("--name", default=None, help="kullanıcının adı (çalışanlar böyle hitap eder)")
    ap.add_argument("--team", default=str(home / "AgentTeam"), help="ekip klasörü (varsayılan ~/AgentTeam)")
    ap.add_argument("--office", default=None, help="Agent Ofisi klasörü (varsayılan <ekip>/Agent Ofisi)")
    ap.add_argument("--lang", default="Türkçe", help="çalışanların konuşacağı dil")
    ap.add_argument("--address", default="Samimi ama profesyonel bir dil kullan.", help="hitap/ton notu")
    ap.add_argument("--prefs", default="", help="ortak tercihler, ';' ile ayrılmış (ör. 'OneDrive kullanma;kısa cevap ver')")
    ap.add_argument("--port", default="4747")
    ap.add_argument("--settings", default=str(home / ".claude" / "settings.json"), help="Claude Code kullanıcı ayar dosyası")
    ap.add_argument("--no-hooks", action="store_true", help="ayar dosyasına dokunma (Agent Ofisi sadece kayıtlardan çalışır)")
    ap.add_argument("--no-launcher", action="store_true", help="~/.local/bin/ekip başlatıcısını kurma")
    ap.add_argument("--force", action="store_true", help="var olan dosyaları yedekleyip yeniden yaz")
    ap.add_argument("--check", action="store_true", help="sadece kontrol et")
    ap.add_argument("--uninstall", action="store_true", help="hook'ları ayarlardan kaldır (dosyalar kalır)")
    a = ap.parse_args()

    team = pathlib.Path(os.path.expanduser(a.team)).resolve()
    office = pathlib.Path(os.path.expanduser(a.office)).resolve() if a.office else team / "Agent Ofisi"
    settings = pathlib.Path(os.path.expanduser(a.settings))

    if a.uninstall:
        s = load_settings(settings)
        n = strip_ours(s)
        if n:
            save_settings(settings, s)
        print(f"{n} hook kaydı kaldırıldı ({settings}). Ekip ve ofis klasörlerine dokunulmadı.")
        return
    if a.check:
        sys.exit(0 if check(team, office, settings) else 1)

    name = a.name or getpass.getuser()
    prefs = "\n".join(f"- {p.strip()}" for p in a.prefs.split(";") if p.strip()) or \
        "- (henüz yok. Çalışanlar kalıcı tercihleri öğrendikçe buraya eklemek için sorar.)"
    print(f"\nAgent Ekip Kiti kuruluyor\n  ekip:  {team}\n  ofis:  {office}\n  kullanıcı: {name}\n")
    team.mkdir(parents=True, exist_ok=True)
    office.mkdir(parents=True, exist_ok=True)

    print("1) Agent Ofisi")
    for f in ["server.py", "index.html", "hook.py"]:
        dst = office / f
        if dst.exists() and not a.force and dst.read_bytes() == (KIT / "office" / f).read_bytes():
            say("=", f"güncel: {dst.name}")
            continue
        if dst.exists():
            shutil.copy2(dst, dst.with_name(dst.name + f".yedek-{STAMP}"))
        shutil.copy2(KIT / "office" / f, dst)
        say("+", f"kopyalandı: {dst}")
    write_launchers(office, a.port)
    (office / "ofis.json").write_text(json.dumps({"team": posix(team)}, ensure_ascii=False) + chr(10), encoding="utf-8")
    say("+", "ofis.json: pano ekip klasörünü ve departmanları tanıyor")

    print("2) Ekip klasörü")
    launcher = office / ("baslat.bat" if os.name == "nt" else "baslat.sh")
    values = {"KULLANICI_ADI": name, "DIL": a.lang, "HITAP": a.address, "TERCIHLER": prefs,
              "EKIP_KLASORU": posix(team), "OFIS_KLASORU": posix(office), "OFIS_BASLAT": posix(launcher),
              "PORT": a.port, "TARIH": TODAY}
    render(KIT / "team" / "ORTAK.md.sablon", team / "ORTAK.md", values, a.force)
    render(KIT / "team" / "EKIP.md.sablon", team / "EKIP.md", values, a.force)
    copytree(KIT / "team" / "Worker Kurucu", team / "Worker Kurucu", a.force)

    if not a.no_launcher:
        write_ekip(team)

    print("3) Claude Code ayarları")
    if a.no_hooks:
        say("=", "atlandı (--no-hooks): Agent Ofisi 'onay bekliyor' durumunu göremez, gerisi çalışır")
    else:
        install_hooks(settings, office)

    ok = check(team, office, settings)
    print(f"""
Sonraki adımlar
  • Agent Ofisi'ni aç:      {launcher}   →  http://localhost:{a.port}
  • İlk çalışanını kur:     {'ekip "Worker Kurucu"' if os.name != 'nt' else 'cd "' + str(team / 'Worker Kurucu') + '"  &&  claude'}   →  /yeni-calisan
  • Ortak kurallar:         {team / 'ORTAK.md'}  (istediğin gibi düzenle)
  • Hook'ları kaldırmak:    python install.py --uninstall --settings "{settings}"
Not: Hook'lar yeni açılan Claude Code oturumlarında devreye girer.
""")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
