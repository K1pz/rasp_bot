# Скрипт для загрузки rasp_bot на GitHub
# Запускайте из папки rasp_bot-main (или укажите путь к ней)

$ErrorActionPreference = "Stop"

# Переходим в папку скрипта (rasp_bot-main)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Папка проекта: $scriptDir" -ForegroundColor Cyan

# 1. Инициализация Git (если ещё не инициализирован)
if (-not (Test-Path ".git")) {
    git init
    Write-Host "Git репозиторий инициализирован." -ForegroundColor Green
} else {
    Write-Host "Git репозиторий уже существует." -ForegroundColor Yellow
}

# 2. Добавляем все файлы
git add -A
Write-Host "Файлы добавлены в индекс." -ForegroundColor Green

# 3. Первый коммит (если нет коммитов)
$commitCount = (git rev-list --count HEAD 2>$null) -as [int]
if (-not $commitCount -or $commitCount -eq 0) {
    git commit -m "Initial commit: rasp_bot"
    Write-Host "Создан начальный коммит." -ForegroundColor Green
} else {
    Write-Host "Коммиты уже есть. Добавьте изменения при необходимости: git add -A; git commit -m 'ваше сообщение'" -ForegroundColor Yellow
}

# 4. Пуш на GitHub (если remote origin уже добавлен)
$remoteOrigin = git remote get-url origin 2>$null
if ($remoteOrigin) {
    git branch -M main 2>$null
    Write-Host "Отправка на GitHub..." -ForegroundColor Cyan
    git push -u origin main
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Код успешно отправлен на GitHub." -ForegroundColor Green
        exit 0
    }
}

# 5. Подсказка по GitHub (если remote не настроен или push не удался)
Write-Host ""
Write-Host "=== Дальнейшие шаги ===" -ForegroundColor Cyan
Write-Host "1. Создайте новый репозиторий на https://github.com/new"
Write-Host "   - Имя, например: rasp_bot"
Write-Host "   - Без README, .gitignore и лицензии (у вас уже есть файлы)"
Write-Host ""
Write-Host "2. Подключите удалённый репозиторий и отправьте код:"
Write-Host "   git remote add origin https://github.com/ВАШ_ЛОГИН/rasp_bot.git"
Write-Host "   git branch -M main"
Write-Host "   git push -u origin main"
Write-Host ""
Write-Host "Или при использовании SSH:"
Write-Host "   git remote add origin git@github.com:ВАШ_ЛОГИН/rasp_bot.git"
Write-Host "   git branch -M main"
Write-Host "   git push -u origin main"
