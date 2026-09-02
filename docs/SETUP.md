# Setup (Windows)

Run these in PowerShell from the project folder.

## 1. Check Python

    py --version

Should report 3.11.9 or newer.

**Use `py`, not `python`, on this machine.** `python` resolves to MSYS2 Python
(`C:\msys64\ucrt64\bin`), which is a Unix-style build: it lays out venvs as
`bin/` instead of `Scripts/`, and PyPI has no wheels matching it, so pandas
would try to compile from C source. The `py` launcher reads the Windows
registry instead of PATH, so it finds the real python.org install.

## 2. Create a virtual environment

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1

Your prompt should now start with `(.venv)`.

If PowerShell blocks the activate script, run this once:

    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

**Why a venv:** it keeps this project's packages separate from your system
Python. Without it, two projects that need different Flask versions fight each
other. Every real Python project does this.

## 3. Install dependencies

    pip install -r requirements.txt

## 4. Initialize git

    git init
    git add .
    git commit -m "Initial scaffold: project plan, structure, dependencies"

## 5. Create the GitHub repo

Make an empty repo named `interntrack` on github.com/stevestea, then:

    git remote add origin https://github.com/stevestea/interntrack.git
    git branch -M main
    git push -u origin main

## Daily workflow

Activate the venv every time you open a new terminal:

    .\.venv\Scripts\Activate.ps1

Commit when something works, not when everything is done. Small commits are
easier to undo and they make the repo look actively developed, which matters
when a recruiter clicks through.
