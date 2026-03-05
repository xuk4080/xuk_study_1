#!/usr/bin/env python3
"""
word_notifier_win.py —— 跨平台浮窗背单词（tkinter，兼容 Windows / macOS / Linux）
词库来自 ToastFish/Resources/inami.db

依赖（仅标准库 + 可选语音）：
    pip install pyttsx3          # Windows/macOS/Linux 语音（可选）

打包为 Windows .exe：
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name 背单词new word_notifier_win.py

用法：
    python word_notifier_win.py
    python word_notifier_win.py --book KrDict_All
    python word_notifier_win.py --interval 30
    python word_notifier_win.py --list
    python word_notifier_win.py --pos left
"""

import sqlite3, time, argparse, os, json, random, re, threading, subprocess, sys
from datetime import date, datetime
import tkinter as tk
from tkinter import font as tkfont

# ── 韩语 RR 罗马字化（本地模块）────────────────────────────────────────────────
try:
    from kr_romanize import korean_to_roman as _kr_roman
except ImportError:
    _kr_roman = None

# ── 路径配置 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_db():
    # PyInstaller 打包后 sys._MEIPASS 是解压目录
    base = getattr(sys, "_MEIPASS", SCRIPT_DIR)
    for candidate in [
        os.path.join(base, "db", "inami.db"),
        os.path.join(SCRIPT_DIR, "db", "inami.db"),
        os.path.join(SCRIPT_DIR, "../ToastFish/Resources/inami.db"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return os.path.join(SCRIPT_DIR, "../ToastFish/Resources/inami.db")

DB_PATH       = _resolve_db()
ECDICT_PATH   = os.path.join(SCRIPT_DIR, "stardict.db")
PROGRESS_FILE = os.path.expanduser("~/.word_notifier_win_progress.json")
NON_WORD_TABLES = {"Count", "Goin", "Global"}

# ── 样式 ──────────────────────────────────────────────────────────────────────
WIN_W         = 460
WIN_H_BASE    = 200        # 基础高度（会根据内容动态撑高）
MARGIN_SIDE   = 20
MARGIN_BOTTOM = 80
BG_COLOR      = "#1E1E2E"  # 深蓝背景
SEP_COLOR     = "#31324A"
CLR_HEAD      = "#CDD6F4"  # 单词
CLR_ROMAN     = "#89B4FA"  # 罗马字/音标（蓝）
CLR_PHONE     = "#737590"  # 韩文发音（灰）
CLR_POS       = "#F38BA8"  # 词性（粉）
CLR_TRAN      = "#A6E3A1"  # 释义（绿）
CLR_SENT      = "#BAC2DE"  # 例句
CLR_SENT_CN   = "#6C7086"  # 例句译文
CLR_PHRASE    = "#FAB387"  # 短语（橙）
CLR_INFO      = "#6C7086"  # 进度/倒计时
CLR_BTN       = "#89B4FA"  # 按钮蓝

# ── 展示时长档位 ──────────────────────────────────────────────────────────────
INTERVAL_STEPS = [15, 30, 60, 120, 300]

# ── 语音朗读 ──────────────────────────────────────────────────────────────────
_tts_engine = None

def _get_tts():
    global _tts_engine
    if _tts_engine is None:
        try:
            import pyttsx3
            _tts_engine = pyttsx3.init()
        except Exception:
            _tts_engine = False
    return _tts_engine if _tts_engine else None

def _speak(text: str):
    """后台朗读：Windows 用 pyttsx3，macOS 兜底用 say 命令"""
    word = text.rstrip("-").strip()
    if not word:
        return
    is_korean = any(0xAC00 <= ord(c) <= 0xD7A3 for c in word)

    def _run():
        # macOS：用系统 say 命令
        if sys.platform == "darwin":
            voice = "Yuna" if is_korean else "Samantha"
            try:
                subprocess.run(["say", "-v", voice, word], timeout=10)
            except Exception:
                pass
            return
        # Windows / Linux：用 pyttsx3
        eng = _get_tts()
        if eng:
            try:
                eng.say(word)
                eng.runAndWait()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()

# ── SM2 算法 ──────────────────────────────────────────────────────────────────
def sm2_next(difficulty, days_between, score):
    q = {0: 1, 1: 3, 2: 5}.get(score, 3)
    new_diff = max(0.1, min(1.0, difficulty + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    new_days = 1.0 if q < 3 else max(1.0, min(days_between * (1 / new_diff), 365.0))
    return new_diff, new_days

# ── 词库操作 ──────────────────────────────────────────────────────────────────
def list_books(db_path):
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall() if r[0] not in NON_WORD_TABLES]
    conn.close()
    return sorted(tables)

def get_due_word(db_path, book):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur   = conn.cursor()
    today = date.today().isoformat()
    cur.execute(f"""
        SELECT * FROM [{book}]
        WHERE dateLastReviewed IS NOT NULL AND dateLastReviewed != 'NULL'
          AND date(dateLastReviewed,'+'||CAST(CAST(daysBetweenReviews AS INT) AS TEXT)||' days') <= date('{today}')
        ORDER BY dateLastReviewed ASC LIMIT 50
    """)
    rows = cur.fetchall()
    if not rows:
        cur.execute(f"""
            SELECT * FROM [{book}]
            WHERE dateLastReviewed IS NULL OR dateLastReviewed = 'NULL'
            ORDER BY wordRank ASC LIMIT 50
        """)
        rows = cur.fetchall()
    if not rows:
        cur.execute(f"SELECT * FROM [{book}] ORDER BY RANDOM() LIMIT 1")
        rows = cur.fetchall()
    conn.close()
    return dict(random.choice(rows)) if rows else None

# ── ECDICT / 韩语补全 ──────────────────────────────────────────────────────────
_ecdict_conn = None

def _get_ecdict_conn():
    global _ecdict_conn
    if _ecdict_conn is None and os.path.exists(ECDICT_PATH):
        _ecdict_conn = sqlite3.connect(ECDICT_PATH)
        _ecdict_conn.row_factory = sqlite3.Row
    return _ecdict_conn

def _is_cjk_or_korean(text):
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3: return True
        if 0x3040 <= cp <= 0x30FF: return True
        if 0x4E00 <= cp <= 0x9FFF: return True
    return False

def enrich_with_ecdict(word_dict):
    head = (word_dict.get("headWord") or "").strip()
    if not head:
        return word_dict

    if _is_cjk_or_korean(head):
        result = dict(word_dict)
        tran = (result.get("tranCN") or "").strip()
        # 词干形补全
        if not tran and head.endswith("-"):
            root = head.rstrip("-")
            try:
                c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row
                for suffix in ("다", "하다", "이다"):
                    row = c.execute(
                        "SELECT tranCN,usphone,pos,sentence,sentenceCN FROM KrDict_All WHERE headWord=? LIMIT 1",
                        (root + suffix,)
                    ).fetchone()
                    if row and (row["tranCN"] or "").strip():
                        for k in ("tranCN","usphone","pos","sentence","sentenceCN"):
                            result[k] = result.get(k) or row[k] or ""
                        tran = result["tranCN"].strip()
                        break
                if not tran:
                    row = c.execute(
                        "SELECT tranCN,usphone,pos FROM KrDict_All WHERE headWord=? AND (tranCN!='' AND tranCN IS NOT NULL) LIMIT 1",
                        (root,)
                    ).fetchone()
                    if row:
                        for k in ("tranCN","usphone","pos"):
                            result[k] = result.get(k) or row[k] or ""
                        tran = result["tranCN"].strip()
                c.close()
            except Exception:
                pass

        # 罗马字
        if _kr_roman:
            phone_src = (result.get("usphone") or "").strip()
            src = (phone_src or head).rstrip("-").replace("ː","").replace(":","")
            roman = _kr_roman(src)
            if roman:
                result["roman"]   = roman
                result["usphone"] = phone_src

        # 分行释义
        tran = (result.get("tranCN") or "").strip()
        if tran:
            lines = [l.strip() for l in re.split(r"[；;、/]+", tran) if l.strip()]
            result["tranLines"] = lines if lines else [tran]
        else:
            result["tranLines"] = []
        return result

    conn = _get_ecdict_conn()
    if conn is None:
        return word_dict
    h = head.lower()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stardict WHERE word=? LIMIT 1", (h,))
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT * FROM stardict WHERE sw=? LIMIT 1", (h,))
        row = cur.fetchone()
    if not row:
        return word_dict
    ec = dict(row)
    result = dict(word_dict)
    if ec.get("phonetic"):
        result["usphone"] = ec["phonetic"]; result["ukphone"] = ""
    tran_raw = (ec.get("translation") or "").strip()
    if tran_raw:
        lines = [l.strip() for l in tran_raw.splitlines() if l.strip()]
        result["tranLines"] = lines
        result["tranCN"]    = "  /  ".join(lines)
        result["pos"] = lines[0].split(".")[0].strip() if lines and ". " in lines[0] else (result.get("pos") or "")
    else:
        result["tranLines"] = [result.get("tranCN","")]
    return result

def update_word(db_path, book, word_rank, score, difficulty, days_between):
    new_diff, new_days = sm2_next(difficulty, days_between, score)
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute(f"""
        UPDATE [{book}]
        SET difficulty=?, daysBetweenReviews=?, lastScore=?, dateLastReviewed=?
        WHERE wordRank=?
    """, (new_diff, new_days, score, date.today().isoformat(), word_rank))
    conn.commit(); conn.close()

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"today": str(date.today()), "count": 0}

def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# tkinter 主应用
# ══════════════════════════════════════════════════════════════════════════════
class WordNotifierApp:
    PAD = 16

    def __init__(self, db_path, book, interval, max_count, position):
        self.db_path   = db_path
        self.book      = book
        self.interval  = interval
        self.max_count = max_count
        self.position  = position

        self.prog = load_progress()
        if self.prog.get("today") != str(date.today()):
            self.prog = {"today": str(date.today()), "count": 0}

        self.all_books    = list_books(db_path)
        self.current_word = None
        self.score        = None
        self.pushed       = 0
        self.history      = []
        self.hist_idx     = -1
        self.next_time    = None
        self._after_id    = None

        self._build_window()
        self._next_word()
        self._tick()
        self.root.mainloop()

    # ── 构建窗口 ──────────────────────────────────────────────────────────────
    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("背单词new")
        self.root.configure(bg=BG_COLOR)
        self.root.overrideredirect(True)   # 无边框
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)

        # Windows 圆角（Win11 支持；其他平台忽略报错）
        try:
            from ctypes import windll, byref, c_int
            HWND_val = windll.user32.GetForegroundWindow()
            windll.dwmapi.DwmSetWindowAttribute(
                self.root.winfo_id(), 33, byref(c_int(12)), 4
            )
        except Exception:
            pass

        # 字体
        self.font_head   = tkfont.Font(family="Microsoft YaHei UI" if sys.platform=="win32" else "PingFang SC",
                                       size=20, weight="bold")
        self.font_roman  = tkfont.Font(family="Consolas" if sys.platform=="win32" else "Menlo", size=13)
        self.font_phone  = tkfont.Font(family="Microsoft YaHei UI" if sys.platform=="win32" else "PingFang SC",
                                       size=10)
        self.font_tran   = tkfont.Font(family="Microsoft YaHei UI" if sys.platform=="win32" else "PingFang SC",
                                       size=12)
        self.font_small  = tkfont.Font(family="Microsoft YaHei UI" if sys.platform=="win32" else "PingFang SC",
                                       size=10)
        self.font_btn    = tkfont.Font(family="Microsoft YaHei UI" if sys.platform=="win32" else "PingFang SC",
                                       size=11)

        # 主 Frame（可拖动）
        self.frame = tk.Frame(self.root, bg=BG_COLOR)
        self.frame.pack(fill="both", expand=True)
        self.frame.bind("<ButtonPress-1>",   self._drag_start)
        self.frame.bind("<B1-Motion>",       self._drag_move)

        # 内容区域（动态重建）
        self.content_frame = tk.Frame(self.frame, bg=BG_COLOR)
        self.content_frame.pack(fill="both", expand=True, padx=self.PAD, pady=(8, self.PAD))

        self._place_window()

    def _place_window(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w  = WIN_W
        # 先以基础高度定位，render 后会调整
        h  = WIN_H_BASE
        if self.position == "right":
            x = sw - w - MARGIN_SIDE
        elif self.position == "left":
            x = MARGIN_SIDE
        else:
            x = (sw - w) // 2
        y = sh - h - MARGIN_BOTTOM
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ── 拖动 ──────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ── 无边框按钮辅助（Label 模拟，避免 macOS 白色方块）────────────────────────
    def _btn(self, parent, text, cmd, fg=None, font=None, pad=(4, 4), side=None, **kw):
        """背景与父容器完全融合，悬停时文字变亮"""
        lbl = tk.Label(parent, text=text,
                       bg=BG_COLOR, fg=fg or CLR_BTN,
                       font=font or self.font_btn,
                       cursor="hand2",
                       padx=pad[0], pady=pad[1], **kw)
        if side:
            lbl.pack(side=side)
        lbl.bind("<Enter>",    lambda e: lbl.config(fg="#FFFFFF"))
        lbl.bind("<Leave>",    lambda e: lbl.config(fg=fg or CLR_BTN))
        lbl.bind("<Button-1>", lambda e: cmd())
        return lbl

    # ── 渲染单词 ──────────────────────────────────────────────────────────────
    def _render(self, word, progress_text):
        # 清除旧内容
        for w in self.content_frame.winfo_children():
            w.destroy()

        p = self.PAD
        cf = self.content_frame

        head      = word.get("headWord", "")
        roman     = (word.get("roman","") or "").strip()
        phone     = (word.get("usphone","") or word.get("ukphone","") or "").strip()
        pos       = (word.get("pos","") or "").strip()
        tran      = (word.get("tranCN","") or "").strip()
        sentence  = (word.get("sentence","") or "").strip()
        sent_cn   = (word.get("sentenceCN","") or "").strip()
        phrase    = (word.get("phrase","") or "").strip()
        phrase_cn = (word.get("phraseCN","") or "").strip()
        tran_lines = word.get("tranLines") or ([tran] if tran else [])

        # ── 顶栏：词库按钮 + 关闭按钮
        top = tk.Frame(cf, bg=BG_COLOR)
        top.pack(fill="x", pady=(0, 2))

        self._btn(top, f"📚 {self.book}", self._show_book_menu,
                  fg=CLR_BTN, font=self.font_small, pad=(0, 0), side="left")
        self._btn(top, "✕", self._close,
                  fg=CLR_INFO, pad=(0, 0), side="right")

        # ── 单词行 + 🔊 📋 按钮
        word_row = tk.Frame(cf, bg=BG_COLOR)
        word_row.pack(fill="x", pady=(2, 0))

        tk.Label(word_row, text=head, bg=BG_COLOR, fg=CLR_HEAD,
                 font=self.font_head, anchor="w").pack(side="left")

        self._btn(word_row, "📋", lambda: self._copy_word(head),
                  fg=CLR_INFO, pad=(4, 0), side="right")
        self._btn(word_row, "🔊", lambda: _speak(head),
                  fg=CLR_INFO, pad=(4, 0), side="right")

        # ── 音标区域
        if roman:
            tk.Label(cf, text=roman, bg=BG_COLOR, fg=CLR_ROMAN,
                     font=self.font_roman, anchor="w").pack(fill="x", pady=(1,0))
            if phone:
                tk.Label(cf, text=f"[{phone}]", bg=BG_COLOR, fg=CLR_PHONE,
                         font=self.font_phone, anchor="w").pack(fill="x")
        elif phone:
            tk.Label(cf, text=f"[{phone}]", bg=BG_COLOR, fg=CLR_ROMAN,
                     font=self.font_roman, anchor="w").pack(fill="x", pady=(1,0))

        # ── 分隔线
        tk.Frame(cf, bg=SEP_COLOR, height=1).pack(fill="x", pady=(6, 4))

        # ── 词性 + 释义（多行）
        for line in tran_lines:
            line = line.strip()
            if not line:
                continue
            if len(line) >= 3 and line[1] == "." and line[2] == " ":
                lp, lt = line[:1], line[3:]
            elif len(line) >= 4 and line[2] == "." and line[3] == " ":
                lp, lt = line[:2], line[4:]
            else:
                lp, lt = "", line

            row = tk.Frame(cf, bg=BG_COLOR)
            row.pack(fill="x", pady=1)
            if lp:
                tk.Label(row, text=lp+".", bg=BG_COLOR, fg=CLR_POS,
                         font=self.font_tran, width=3, anchor="w").pack(side="left")
            tk.Label(row, text=lt, bg=BG_COLOR, fg=CLR_TRAN,
                     font=self.font_tran, anchor="w", wraplength=WIN_W-p*2-30,
                     justify="left").pack(side="left", fill="x")

        # ── 例句
        if sentence:
            tk.Label(cf, text=f"📝  {sentence}", bg=BG_COLOR, fg=CLR_SENT,
                     font=self.font_small, anchor="w", wraplength=WIN_W-p*2,
                     justify="left").pack(fill="x", pady=(6,0))
        if sent_cn:
            tk.Label(cf, text=f"    {sent_cn}", bg=BG_COLOR, fg=CLR_SENT_CN,
                     font=self.font_small, anchor="w", wraplength=WIN_W-p*2,
                     justify="left").pack(fill="x")

        # ── 短语
        if phrase:
            tk.Label(cf, text=f"💡  {phrase}  {phrase_cn}", bg=BG_COLOR, fg=CLR_PHRASE,
                     font=self.font_small, anchor="w", wraplength=WIN_W-p*2,
                     justify="left").pack(fill="x", pady=(4,0))

        # ── 分隔线
        tk.Frame(cf, bg=SEP_COLOR, height=1).pack(fill="x", pady=(6, 4))

        # ── 底栏：◀ ▶ | 进度 | 倒计时 | - 时长 +
        bot = tk.Frame(cf, bg=BG_COLOR)
        bot.pack(fill="x")

        # 导航
        self._btn(bot, "◀", self._prev_word, side="left")
        self._btn(bot, "▶", self._next_word, side="left")

        # 时长调节（右侧）
        def _fmt_iv(s): return f"{s}s" if s < 60 else f"{s//60}m"
        self._btn(bot, "+", lambda: self._adj_interval(+1), side="right")
        self._iv_lbl = tk.Label(bot, text=_fmt_iv(self.interval),
                                bg=BG_COLOR, fg=CLR_INFO, font=self.font_small)
        self._iv_lbl.pack(side="right", padx=2)
        self._btn(bot, "-", lambda: self._adj_interval(-1), side="right")

        # 进度 + 倒计时
        self._progress_lbl = tk.Label(bot, text=progress_text,
                                      bg=BG_COLOR, fg=CLR_INFO, font=self.font_small)
        self._progress_lbl.pack(side="left", padx=(12, 0))
        self._countdown_lbl = tk.Label(bot, text="",
                                       bg=BG_COLOR, fg=CLR_INFO, font=self.font_small)
        self._countdown_lbl.pack(side="left", padx=(6, 0))

        # ── 调整窗口高度适配内容
        self.root.update_idletasks()
        h = self.frame.winfo_reqheight() + self.PAD * 2
        h = max(h, WIN_H_BASE)
        cur_geo = self.root.geometry()
        m = re.match(r"\d+x\d+\+(-?\d+)\+(-?\d+)", cur_geo)
        if m:
            x, y = int(m.group(1)), int(m.group(2))
            # 保持顶部对齐：y 不变，向下扩展
            self.root.geometry(f"{WIN_W}x{h}+{x}+{y}")

    # ── 词库菜单（Toplevel 模拟下拉）────────────────────────────────────────────
    def _show_book_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg="#2A2A3E", fg="white",
                       activebackground=CLR_BTN, activeforeground="white",
                       font=self.font_small)
        friendly = {
            "CET4_1":"四级 CET-4","CET4_3":"四级 CET-4 (3)",
            "CET6_1":"六级 CET-6","CET6_3":"六级 CET-6 (3)",
            "KaoYan_1":"考研 (1)","KaoYan_2":"考研 (2)",
            "IELTS_3":"雅思 IELTS","TOEFL_2":"托福 TOEFL",
            "GRE_2":"GRE","GMAT_3":"GMAT","SAT_2":"SAT",
            "Level4_1":"英语专四","Level4luan_2":"英语专四乱序",
            "Level8_1":"英语专八","Level8luan_2":"英语专八乱序",
        }
        for b in self.all_books:
            name  = friendly.get(b, b)
            label = f"✓  {name}" if b == self.book else f"    {name}"
            menu.add_command(label=label, command=lambda bk=b: self._switch_book(bk))
        try:
            menu.tk_popup(self.root.winfo_rootx() + self.PAD,
                          self.root.winfo_rooty() + 30)
        finally:
            menu.grab_release()

    def _switch_book(self, new_book):
        if new_book != self.book:
            self.book = new_book
            self._next_word()

    # ── 复制单词 ──────────────────────────────────────────────────────────────
    def _copy_word(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ── 时长调节 ──────────────────────────────────────────────────────────────
    def _adj_interval(self, delta):
        steps = INTERVAL_STEPS
        try:
            idx = steps.index(self.interval)
        except ValueError:
            idx = 2
        self.interval = steps[max(0, min(len(steps)-1, idx+delta))]
        self.next_time = time.time() + self.interval
        if hasattr(self, "_iv_lbl"):
            def _fmt(s): return f"{s}s" if s < 60 else f"{s//60}m"
            self._iv_lbl.config(text=_fmt(self.interval))

    # ── 上一个 ────────────────────────────────────────────────────────────────
    def _prev_word(self):
        hist = self.history
        idx  = self.hist_idx
        new_idx = (len(hist) - 2) if idx == -1 else (idx - 1)
        if new_idx < 0 or not hist:
            return
        self.hist_idx     = new_idx
        self.current_word = hist[new_idx]
        self.next_time    = time.time() + self.interval
        cur_book = self.current_word.get("_book", self.book)
        self._render(self.current_word, f"{cur_book}  |  今日第 {self.prog['count']} 个")

    # ── 下一个 ────────────────────────────────────────────────────────────────
    def _next_word(self):
        # 在历史中间时，▶ 直接走历史
        hist = self.history
        idx  = self.hist_idx
        if idx != -1 and idx < len(hist) - 1:
            new_idx = idx + 1
            self.hist_idx = new_idx if new_idx < len(hist) - 1 else -1
            self.current_word = hist[new_idx]
            self.next_time = time.time() + self.interval
            cur_book = self.current_word.get("_book", self.book)
            self._render(self.current_word, f"{cur_book}  |  今日第 {self.prog['count']} 个")
            return

        if self.max_count > 0 and self.pushed >= self.max_count:
            self._close()
            return

        word = get_due_word(self.db_path, self.book)
        if not word:
            self._close()
            return
        word = enrich_with_ecdict(word)

        # 保存上一个评分
        prev = self.current_word
        if prev is not None:
            sc = self.score if self.score is not None else 1
            update_word(self.db_path, prev.get("_book", self.book),
                        prev["wordRank"], sc, prev["difficulty"], prev["daysBetweenReviews"])
            save_progress(self.prog)

        word["_book"]     = self.book
        self.pushed      += 1
        self.score        = None
        self.current_word = word
        self.hist_idx     = -1
        self.next_time    = time.time() + self.interval
        self.prog["count"] += 1

        self.history.append(word)
        if len(self.history) > 50:
            self.history.pop(0)

        progress_text = f"{self.book}  |  今日第 {self.prog['count']} 个"
        self._render(word, progress_text)

    # ── 心跳（倒计时 + 自动换词）──────────────────────────────────────────────
    def _tick(self):
        if not hasattr(self, "root") or not self.root.winfo_exists():
            return
        now    = time.time()
        remain = (self.next_time - now) if self.next_time else 0
        if hasattr(self, "_countdown_lbl"):
            try:
                self._countdown_lbl.config(
                    text=f"⏱ {int(remain)}s" if remain > 0 else ""
                )
            except Exception:
                pass
        if self.next_time and now >= self.next_time:
            self._next_word()
        self._after_id = self.root.after(200, self._tick)

    # ── 关闭 ──────────────────────────────────────────────────────────────────
    def _close(self):
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self.root.destroy()


# ── 入口 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="跨平台浮窗背单词（tkinter）")
    parser.add_argument("--book",     default="KrDict_All")
    parser.add_argument("--interval", default=60, type=int)
    parser.add_argument("--count",    default=0,  type=int)
    parser.add_argument("--list",     action="store_true")
    parser.add_argument("--pos",      default="right", choices=["right","left","center"])
    parser.add_argument("--db",       default=DB_PATH)
    args = parser.parse_args()

    db = os.path.abspath(args.db)
    if not os.path.exists(db):
        print(f"❌ 找不到词库：{db}"); return

    if args.list:
        for b in list_books(db): print(f"  {b}")
        return

    books = list_books(db)
    if args.book not in books:
        print(f"❌ 词库 '{args.book}' 不存在，可用：{', '.join(books)}"); return

    iv = args.interval
    if iv not in INTERVAL_STEPS:
        iv = min(INTERVAL_STEPS, key=lambda s: abs(s - iv))

    WordNotifierApp(db, args.book, iv, args.count, args.pos)


if __name__ == "__main__":
    main()
