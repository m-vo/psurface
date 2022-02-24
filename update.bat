@echo off

@setlocal enableextensions
@cd /d "%~dp0"

set branch=main
set /p branch="Enter target branch/tag/commit (main): "

git stash
git checkout %branch%
git pull
pipenv sync
