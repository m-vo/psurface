@echo off

@setlocal enableextensions
@cd /d "%~dp0"

git pull
pipenv sync
