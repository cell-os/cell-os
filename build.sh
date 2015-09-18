#!/bin/bash

# build script - meant to be run on build server
# cleans up build directory and copies everything in a structure
# that can be used for promotion

VERSION=$(cat VERSION)

rm -rf build
mkdir build

cp cell-os-base.yaml build/cell-os-base-${VERSION}.yaml
cp deploy/aws/elastic-cell.json build/elastic-cell-${VERSION}.json
cp cell build/cell
cp build.sh build/
cp VERSION build/


