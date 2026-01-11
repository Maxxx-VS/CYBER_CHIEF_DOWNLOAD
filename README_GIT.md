# Для отправки на удаленый репозиторий CYBER_CHIEF_DOWNLOAD всей директории cyber_chief

## полностью перезаписать директорию на git
cd ~/cyber_chief
git add -A
git commit -m "КИБЕР-ШЕФ ВЕРСИЯ={} от $(date +'%Y-%m-%d %H:%M')"
git push --force origin main


## перезаписать изменения в директории на git
git pull --rebase origin main
git add .
git status
git commit -m "КИБЕР-ШЕФ ВЕРСИЯ={} от $(date +'%Y-%m-%d %H:%M')"
git push origin main


