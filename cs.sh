#!/usr/bin/env bash

./.venv/bin/black .
./.venv/bin/isort .

for i in $(find . -not -path '*/.*' -type f -name '*.py');
do
  if ! grep -q LICENSE "$i"
  then
    cat .header.py "$i" >> "$i.tmp" && mv "$i.tmp" "$i"
    echo "Added license header to $i"
  fi
done
