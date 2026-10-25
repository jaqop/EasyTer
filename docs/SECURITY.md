# Security

## NTLM leaks through terminal paths

Windows sends the user's NTLM credentials when a process touches a UNC path.
`os.path.isdir`, `os.stat`, `open`, and `GetFullPathName` (`os.path.abspath`)
all do that touch. Terminal output is untrusted: a program, a log, or a
remote shell can emit OSC sequences. EasyTer must not pass those paths, or
paths derived from them, to the filesystem.

### The gate

`accept_local_path(path)` in `easyterpro/localpath.py` is the only check.
It returns a normalized `X:\...` path, or `None`. It is lexical: it never
calls the filesystem.

Before the check it percent-decodes (repeatedly) and applies NFKC, so a
separator hidden as `%5C`, `%2F`, `%255C`, or a fullwidth / small solidus is
judged as the separator it becomes. The decoded spelling and the NFKC
spelling both have to pass. NFKC is only a check: the returned string keeps
the original characters, so a name such as `ﬁle.txt` is not rewritten to
`file.txt`. `.` and `..` are still collapsed with `ntpath.normpath`, and
that normalized result is checked again.

Accepted: an absolute path with a drive letter, after that normalization.
`C:\Users\x` and `D:\proj\مشروع` pass. `..` and `.` are collapsed first, and
the result still has to be a local drive path.

Rejected:

- UNC in every form: `\\host`, `//host`, `\\?\`, `\\.\`, `\??\`, `\\?\UNC\`,
  `//?/UNC/`, and WebDAV authorities such as `\\host@SSL\`, `\\host@8080\`,
  and `\\host@SSL@443\DavWWWRoot`.
- `file:` URLs, including `file://///host/share`.
- Mixed `\` and `/` separators.
- Control characters and bidi controls (overrides, embeds, isolates, LRM, RLM,
  ALM). These can also spoof the path shown in a confirmation dialog.
- A `:` after the drive letter (an NTFS alternate data stream), including one
  that `normpath` would later walk out of with `..`.
- DOS device names in any component: `CON`, `NUL`, `PRN`, `AUX`, `CONIN$`,
  `CONOUT$`, `CLOCK$`, `COM0`–`COM9`, `LPT0`–`LPT9`, including `NUL.txt`,
  trailing dots, and trailing spaces.
- `"` and `,`.
- Anything that is not a drive-absolute path (`C:relative`, `\Windows`, a
  POSIX path).

A mapped drive letter (`Z:\...`) passes this lexical check. `GetDriveTypeW`
then rejects it when the letter is remote, missing, or unknown. A literal
UNC home (`\\server\users\name`) fails the lexical check. Shells then start
at the system drive root instead of that share.

### Where it is applied

- **OSC 9;9** and **OSC 7** working-directory reports, before `isdir`. The
  directory stored on the session is the gated path, so a later tab or split
  inherits that rather than the raw report.
- **OSC 7 host.** The URI host must be empty or `localhost` (case-insensitive).
  Any other host, including `wsl.local` and `127.0.0.1`, drops the report
  before the path is converted into a filesystem call.
- **OSC 6969** (`edit`). A rejected path is not emitted, not opened, and not
  written into the session file. An accepted path is shown verbatim in a
  confirmation dialog; nothing is opened if the dialog is cancelled. Each
  terminal shows at most one of these dialogs at a time. Further requests
  while it is open are dropped, and another dialog cannot open until one
  second after the previous one closed.
- **Ctrl+click** on a file reference. A relative path such as `src/app.py:12`
  has its line suffix removed and its `/` converted to `\` before it is
  joined with the shell cwd. `~/x.py` is expanded against the home directory.
  The joined path is gated, and only then passed to `isfile`. Moving the
  mouse with Ctrl held does not call `isfile` or `GetDriveTypeW`. The hand
  cursor is shown only when a check run off that path has already found that
  the file exists. A missing file does not get the hand. A drive letter
  already known to be remote, missing, or unknown is not hoverable.
- **Drive type.** After the gate and immediately before `isdir`, `isfile`,
  or `open` on a terminal-derived path, `GetDriveTypeW` is called fresh and
  must report a local drive. `DRIVE_REMOTE`, `DRIVE_NO_ROOT_DIR`, and
  `DRIVE_UNKNOWN` are rejected. A per-letter cache is kept for hover hints
  only and is not consulted for that decision, so a letter that is later
  mapped to a share cannot be touched on the strength of an old answer. The
  root passed to `GetDriveTypeW` is a Python `str` (`c_wchar_p`), not an
  ANSI string.
- **Start directory** for new tabs and splits (`resolve_start_dir`), and the
  folder argument on the command line (`start_dir_from_argv`). Relative
  command-line arguments are joined lexically with the process cwd.
  `os.path.abspath` is not used, because on Windows it calls
  `GetFullPathName`.
- **Session restore.** `serialize_node` stores an editor path only when the
  gate accepts it. `build_node` runs the gate again before the editor opens
  the file, so a hand-edited `easyter_session.json` cannot introduce a UNC
  path.
- **File dialogs.** A path the user picks in Open or Save As is not terminal
  output, and the gate is not applied to it. A failed save of a path that
  *did* come from the terminal leaves an error in the editor header instead
  of clearing it.

### Local symlinks

The gate does not resolve symlinks, because that resolution is a filesystem
call. A local path such as `C:\Users\x\link` passes even when the link's
target is a UNC path, and opening it makes Windows authenticate to that
target. Creating the link requires the symlink privilege (or Developer
Mode). EasyTer does not create it.

### Input that is not only a path

The path `accept_local_path` returns is a Python `str`. It is passed to
`GetDriveTypeW` as `c_wchar_p` and to Python's own path functions (`isdir`,
`isfile`, `open`). It is not encoded with the ANSI code page, and it is not
passed to an `*A` Win32 API. `bytes` would best-fit.

A dropped file with no shell metacharacter is wrapped in double quotes. A
backslash is a path separator, not a metacharacter, except when the path
ends in one (`"C:\"` escapes the closing quote). A metacharacter or a
trailing backslash is quoted for the pane's shell and shown before it is
written; the inserted text is that quoted form. Format characters are shown
on the card as `<U+XXXX>`. A Unicode control character refuses the drop.
Dropped text is not quoted as a path: newlines become a space, every other
control character (C0, DEL, and C1) is removed, then the paste guard runs.

`quote_shell_path` is used when the command is known to be PowerShell (the
oh-my-posh lines). It refuses a control character. PowerShell single quotes
double `'`, U+2018, U+2019, U+201A, and U+201B, because PowerShell treats all
five as quotes. cmd still refuses `"` and `%` and a trailing `^`.
`accept_local_path` is not the quoter: it accepts `'`, `;`, `&`, `$(` and
backticks.

OSC 52 clipboard writes are off unless `osc52_clipboard` is enabled. When it
is on, each write asks for confirmation and is limited to 1 MB. An OSC 52
query is never answered.

Paste in EasyTer Pro uses the same guard as EasyTer: a warning for multi-line
text, control characters, and large pastes, then bracketed-paste wrapping
when the program asked for it. ESC and U+009B are removed from the pasted
text so a nested bracket-end marker cannot close the paste.

The oh-my-posh theme path written into a live PowerShell pane, into a new
PowerShell tab, and into `$PROFILE` passes the PowerShell quoter above. A
name that leaves the themes directory is not written. A `$PROFILE` theme
name has to be a plain filename, and the path is single-quoted.
