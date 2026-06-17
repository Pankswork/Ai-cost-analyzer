#!/bin/bash
set -euo pipefail

rm -rf package
mkdir -p package

pip install -r requirements.txt --platform manylinux2014_x86_64 --target package/ --only-binary=:all:
cp handler.py package/
cd package && zip -r ../log-analysis.zip .
cd ..
rm -rf package

echo "Created log-analysis.zip"
