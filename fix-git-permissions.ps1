# Скрипт для исправления прав доступа к .git директории
# Запустите этот скрипт от имени администратора

$gitDir = Join-Path $PSScriptRoot ".git"

Write-Host "Исправление прав доступа к .git директории..." -ForegroundColor Yellow

# Удаляем DENY правила
icacls $gitDir /remove "S-1-5-21-416741754-1679342226-2330601608-2779582006" /T 2>&1 | Out-Null
icacls $gitDir /remove "S-1-5-21-1539323242-1323947827-118282611-3014874451" /T 2>&1 | Out-Null

# Устанавливаем полные права для текущего пользователя
icacls $gitDir /grant "${env:USERNAME}:(OI)(CI)F" /T 2>&1 | Out-Null

Write-Host "Права доступа исправлены!" -ForegroundColor Green
Write-Host "Теперь можно выполнить: git add -A" -ForegroundColor Green
