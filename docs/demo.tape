# Dónde se guarda el GIF
Output docs/demo3.gif

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
Type "sqlite3 -box resultados/kids.db"
Sleep 600ms
Enter
Type "SELECT * FROM ultimos ORDER BY ter;"
Sleep 600ms
Enter
Wait
Sleep 5s