' يشغّل EasyTer بلا نافذة كونسول سوداء
Set sh = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = scriptDir
' Python 3.13: pywinpty 2.x (stable, no freeze) has no wheel for 3.14
sh.Run "pyw.exe -3.13 """ & scriptDir & "\EasyTer.py""", 0, False
