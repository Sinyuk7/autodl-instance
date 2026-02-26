#!/bin/bash
# AutoDL Instance 一键初始化
# 用法: ./init.sh [--debug]

cd "$(dirname "$0")"
python -m src.main setup "$@"
