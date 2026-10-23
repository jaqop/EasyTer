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
judged as the separator it becomes. The decoded spelling and the on-disk
spelling both have to pass. The returned string is the on-disk spelling,
which is what a later `isdir` or `open` would receive. It is normalized with
`ntpath.normpath` and checked again afterwards.

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
- DOS device names in any component: `CON`, `NUL`, `PRN`, `AUX`, `COM0`–`COM9`,
  `LPT0`–`LPT9`, including `NUL.txt`, trailing dots, and trailing spaces.
- `"` and `,`.
- Anything that is not a drive-absolute path (`C:relative`, `\Windows`, a
  POSIX path).

A mapped drive letter (`Z:\...`) is a local path for this check. A literal
UNC home (`\\server\users\name`) is not. Shells then start at the system
drive root instead of that share.

### Where it is applied

- **OSC 9;9** and **OSC 7** working-directory reports, before `isdir`. The
  directory stored on the session is the gated path, so a later tab or split
  inherits that rather than the raw report.
- **OSC 7 host.** The URI host must be empty or `localhost` (case-insensitive).
  Any other host, including `wsl.local` and `127.0.0.1`, drops the report
  before the path is converted into a filesystem call.
- **OSC 6969** (`edit`). A rejected path is not emitted, not opened, and not
  written into the session file. An accepted path is shown verbatim in a
  confirmation dialog; nothing is opened if the dialog is cancelled.
- **Ctrl+click** on a file reference. Relative paths are joined lexically with
  the shell cwd, then gated, and only then passed to `isfile`.
- **Start directory** for new tabs and splits (`resolve_start_dir`), and the
  folder argument on the command line (`start_dir_from_argv`). Relative
  command-line arguments are joined lexically with the process cwd.
  `os.path.abspath` is not used, because on Windows it calls
  `GetFullPathName`.
- **Session restore.** `serialize_node` stores an editor path only when the
  gate accepts it. `build_node` runs the gate again before the editor opens
  the file, so a hand-edited `easyter_session.json` cannot introduce a UNC
  path.

Dragging a file onto the terminal, OSC 52, paste protection, and the
oh-my-posh prompt are separate from this gate.
