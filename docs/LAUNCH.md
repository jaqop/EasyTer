# EasyTer — launch kit

Copy-paste posts for launching EasyTer. Goal of launch #1: **get users**, not revenue.
Post the same day across channels, then reply to every comment for the first 48 hours —
early engagement is what makes these threads climb.

**Before you post:** make sure the `v1.0.0` release has `EasyTer.exe` attached, the
landing page is live (GitHub Pages → Settings → Pages → `main` / `/docs`), and you have
a fresh side-by-side screenshot (broken Arabic in Windows Terminal vs. correct in EasyTer).
That screenshot is your single most important asset — the whole pitch is visual.

---

## 1. Hacker News — "Show HN"

**Title** (keep it plain; HN hates hype):
```
Show HN: EasyTer – a Windows terminal that renders connected Arabic correctly
```

**First comment** (post this yourself immediately after submitting):
```
I'm the author. I built EasyTer because no Windows terminal renders Arabic
correctly. Windows Terminal, kitty, Alacritty, WezTerm — they all show Arabic
as disconnected, isolated letters in reversed order, because they don't do
letter joining (shaping) or the Unicode bidirectional algorithm. For a
right-to-left, cursive script that's the difference between readable and
gibberish.

EasyTer renders every terminal line through Qt's QTextLayout, which embeds
HarfBuzz shaping and UAX #9 BiDi — the same machinery native Linux terminals
implement by hand. It runs a real ConPTY (via pywinpty) on a pyte VT emulator,
so interactive programs (PowerShell, vim, git, WSL, Claude Code) work normally,
with correct Arabic on top.

The same engine also handles Persian, Urdu, and Pashto.

It's free, MIT-licensed, Windows-only, no telemetry. Single .exe, no Python
needed. Source and download: https://github.com/jaqop/EasyTer

Happy to go into the shaping/BiDi details — reversing text at the terminal
layer vs. the render layer was the tricky part, especially for full-screen TUI
apps that pre-reverse their own Arabic.
```

Tips: submit Tue–Thu, ~8–10am US Eastern. Don't ask for upvotes (bannable). Answer
technical questions in depth — HN rewards the author who explains *how* it works.

---

## 2. Reddit — r/commandline, r/programming, r/arabs, r/Emirates, r/saudiarabia

**Title:**
```
I built a free Windows terminal that finally renders Arabic connected and in the right order
```

**Body:**
```
Every Windows terminal I tried — Windows Terminal, WezTerm, Alacritty, kitty —
shows Arabic broken: letters disconnected and the reading order reversed.
None of them do Arabic shaping or the bidirectional algorithm.

So I built EasyTer. It renders each line through HarfBuzz shaping + Unicode
BiDi, so Arabic comes out joined, shaped, and right-to-left — even inside vim,
git, and other full-screen programs. Same engine handles Persian, Urdu, and
Pashto too.

It's a full terminal: tabs, split panes, 15+ themes, a built-in editor, a
Python plugin API, Quake-style global hotkey, and it runs PowerShell/cmd/Git
Bash/WSL. Free, open source (MIT), no telemetry, single .exe — no Python setup.

Before/after screenshot and download: <link>
GitHub: https://github.com/jaqop/EasyTer

Feedback very welcome — especially from anyone who works in Arabic/Persian/Urdu
on the command line.
```

Note: read each subreddit's self-promo rules first; lead with the screenshot in
image-friendly subs.

---

## 3. X / Twitter thread

```
1/ Every Windows terminal renders Arabic wrong.

Letters come out disconnected, in reversed order — unreadable.

So I built EasyTer: a free terminal that renders Arabic *correctly*. 🧵
[attach the before/after image]

2/ The problem: Arabic is cursive and right-to-left. Rendering it needs two
things terminals skip — "shaping" (joining letters into their connected forms)
and the bidirectional algorithm (ordering RTL text correctly).

Windows Terminal, kitty, WezTerm, Alacritty: none do it.

3/ EasyTer runs every line through HarfBuzz shaping + Unicode BiDi (UAX #9) via
Qt's QTextLayout. It's a real terminal on ConPTY — vim, git, WSL, PowerShell all
work, with correct Arabic on top.

4/ It's not Arabic-only. The same engine handles Persian, Urdu, and Pashto —
scripts that ~500M+ people write, and that no Windows terminal supports.

5/ Free. Open source (MIT). No telemetry. One .exe, no Python needed.

⬇ Download + source: https://github.com/jaqop/EasyTer

RTs appreciated — someone in your timeline codes in Arabic and needs this.
```

---

## 4. Arabic communities (post in Arabic)

For Arabic dev groups on X, Telegram, Discord, and LinkedIn (MENA tech).

```
أخيراً: طرفيّة (Terminal) لويندوز تعرض العربية موصولةً ومرتّبةً بشكل صحيح.

كل الطرفيّات على ويندوز — Windows Terminal وWezTerm وAlacritty وkitty — تعرض
العربية مقطّعة الحروف ومعكوسة الترتيب، لأنها لا تطبّق وصل الحروف (shaping) ولا
خوارزمية الاتجاه الثنائي (BiDi).

صنعتُ EasyTer لحل هذه المشكلة: يرسم كل سطر عبر HarfBuzz وBiDi، فتظهر العربية
موصولةً وصحيحةً — حتى داخل vim وgit. ويدعم كذلك الفارسية والأردية والبشتو.

مجاني ومفتوح المصدر، بلا تتبّع، ملف exe واحد بلا حاجة إلى Python.

التحميل والمصدر: https://github.com/jaqop/EasyTer

جرّبوه وأخبروني برأيكم 🙏
```

---

## 5. Where else to post

- **dev.to / Hashnode** — a short write-up: "Why no Windows terminal renders Arabic,
  and how I fixed it." Technical posts on shaping/BiDi do well and rank on Google.
- **Product Hunt** — schedule a launch once you have a landing page + a GIF.
- **Lobsters** (needs an invite) — the `unix`/`programming` tags.
- **LinkedIn** — frame it for MENA companies/government: "Arabic-correct developer
  tooling." This is where enterprise leads come from.
- **GitHub topics** — add `terminal`, `arabic`, `rtl`, `bidi`, `windows`, `harfbuzz`,
  `pyside6` to the repo so it's discoverable.

## Follow-through (turns a launch into a business)

1. Add a "⭐ Star on GitHub" ask at the end of every thread — stars are social proof
   for the next visitor and for potential acquirers.
2. Put an email-capture / "Business & support" link on the landing page. Measure demand
   before building paid features.
3. Reply to *everyone* for 48h. The first 20 real users tell you what to build next.
4. Screenshot any praise/notable usage — that's your marketing and your sales deck.
