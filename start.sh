#!/bin/bash
echo "Installing requirements..."
pip3 install -r requirements.txt
echo "Starting Data Analyst Telegram Bot..."
python3 bot.py
