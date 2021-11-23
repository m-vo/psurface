@echo off
:Start
pipenv run python -u psurface.py

TIMEOUT /T 3
GOTO:Start