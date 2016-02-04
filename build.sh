#!/bin/bash

# build script - meant to be run on build server
# cleans up build directory and copies everything in a structure
# that can be used for promotion
# Typical use would be:
#
#   VERSION=$(cat VERSION)
#   bash build.sh "https://s3.amazonaws.com/saasbase-repo/cell-os/\
#   deploy/aws/elastic-cell-scaling-group-${VERSION}.json"

set -e
VERSION=$(cat VERSION)

virtualenv env
source env/bin/activate
pip install -r requirements.txt

rm -rf build
mkdir build

cp cell-os-base.yaml build/cell-os-base-${VERSION}.yaml
./cell build build --template-url $1
cp .generated/build/elastic-cell.json \
  build/elastic-cell-${VERSION}.json
cp .generated/build/elastic-cell-scaling-group.json \
  build/elastic-cell-scaling-group-${VERSION}.json
cp .generated/build/seed.tar.gz build/seed-${VERSION}.tar.gz
cp cell build/cell
cp VERSION build/

