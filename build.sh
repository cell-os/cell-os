#!/bin/bash

# build script - meant to be run on build server
# cleans up build directory and copies everything in a structure
# that can be used for promotion
set -e
VERSION=$(cat VERSION)

pip install -r requirements.txt

rm -rf build
mkdir build

cp cell-os-base.yaml build/cell-os-base-${VERSION}.yaml
./cell build $1
cp deploy/aws/build/elastic-cell.json \
  build/elastic-cell-${VERSION}.json
cp deploy/aws/build/elastic-cell-scaling-group.json \
  build/elastic-cell-scaling-group-${VERSION}.json
cp deploy/seed.tar.gz build/seed-${VERSION}.tar.gz
cp cell build/cell
cp build.sh build/
cp VERSION build/

