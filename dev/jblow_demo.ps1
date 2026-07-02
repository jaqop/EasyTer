# jblow_demo.ps1 — proof that EasyTer renders ANSI syntax colors using its palette.
# Run inside EasyTer Pro:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\Admin\EasyTer\jblow_demo.ps1"
# ANSI 16-color codes map to the active theme palette, so green = the theme's green
# (in the "Jonathan Blow" theme that is #44b340 — his comment green).

$e = [char]27
function c($code, $text) { "$e[${code}m$text$e[0m" }

(c 32 "// nocheckin: this comment is GREEN -- exactly like Jonathan Blow's editor")
""
"$(c 97 'is_interruptible_player_move') :: (t: $(c 33 '*Move_Transaction')) -> (single: $(c 33 '*Single_Move')) {"
"    $(c 32 '// nocheckin explain')"
"    $(c 97 'if') !(t.flags & .PHYSICALLY_MOVED) $(c 97 'return') null;"
"    length := length(single.move_info.delta);"
"    log_error($(c 36 '""In held_keys_go*, got a weird vector""'));"
"    $(c 97 'return') single;"
"}"
""
(c 90 "^ comments green, keywords white, strings cyan -- all drawn with EasyTer's palette.")
(c 90 "  A terminal only shows colors a PROGRAM emits. bat/vim/emacs do this for real files.")
