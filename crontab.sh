#!/bin/bash

# Used to create base .spec (needs manual modification)
# pyinstaller __main__.py -n aw-server

echo "Starting report..."

source /home/nccsoft/komutracker/venv/bin/activate
python /home/nccsoft/komutracker/aw-server/report_spent_time.py