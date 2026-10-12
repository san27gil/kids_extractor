# Dónde se guarda el GIF
Output docs/demo.gif

# Aspecto: ajusta Width si la tabla se corta
Set Shell "zsh"
Set FontSize 16
Set Width 1400
Set Height 750
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms
Set WaitTimeout 5m

# Preparación invisible: base de datos limpia
Hide
Type "rm -rf /tmp/kids_demo && clear"
Enter
Show

# Lo que se ve
Type ".venv/bin/python extraer.py --salida /tmp/kids_demo"
Sleep 600ms
Enter
Wait
Sleep 5s