#!/usr/bin/env bash
# Zatrzymuje skrypt, jeśli wystąpi jakikolwiek błąd
set -o errexit

# Instalacja zależności
pip install -r requirements.txt

# Zbieranie plików statycznych (Tailwind/CSS)
python manage.py collectstatic --no-input


python manage.py migrate