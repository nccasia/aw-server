#!/bin/bash
cp config_ex.py config_ex1.py

sed "s/SV_HOST/$SERVER_HOST/g" -i config.py
sed "s/SV_PORT/$SERVER_PORT/g" -i config.py
sed "s/DB_HOST/$DB_HOST/g" -i config.py
sed "s/DB_PORT/$DB_PORT/g" -i config.py
