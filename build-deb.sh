#!/bin/bash

set -e

PACKAGE_NAME="rhythmbox-telegram-plugin"
VERSION="1.0"
DEB_VERSION="${VERSION}-1"

ROOT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEB_DIR="${ROOT_DIR}/build/${PACKAGE_NAME}_${DEB_VERSION}_all"
DATA_DIR="${DEB_DIR}/data"

# clear
rm -rf "${ROOT_DIR}/build"
# make dirs
mkdir -p "${DATA_DIR}"
mkdir -p "${DATA_DIR}/lib"
mkdir -p "${DATA_DIR}/share"
mkdir -p "${DATA_DIR}/share/icons"
mkdir -p "${DEB_DIR}/debian"

# copy debian data
rsync -a "${ROOT_DIR}/debian/"     "${DEB_DIR}/debian/"
sed -i "s/{VERSION}/DEB_VERSION/g" "${DEB_DIR}/debian/control"
# copy plugin files
rsync -a --include="*.py" --include="*.plugin" --include="LICENCE" --include="*gschema*" --exclude="*" "${ROOT_DIR}/" "${DATA_DIR}/lib/"
rsync -a --include="LICENCE" --include="*gschema*" --exclude="*" "${ROOT_DIR}/" "${DATA_DIR}/share/"
rsync -a "${ROOT_DIR}/icons/hicolor/"   "${DATA_DIR}/share/icons/hicolor/"
rsync -a "${ROOT_DIR}/images/"          "${DATA_DIR}/share/images/"
rsync -a "${ROOT_DIR}/ui/"              "${DATA_DIR}/share/ui/"
rsync -a "${DEB_DIR}/debian/copyright"  "${DATA_DIR}/copyright"

# install plugin requirements
pip3 install -r "${ROOT_DIR}/requirements.txt" -t "${DATA_DIR}/lib/lib"

# build deb
pushd "${DEB_DIR}"
find . | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs rm -rf
tar -czf "${ROOT_DIR}/build/${PACKAGE_NAME}_${VERSION}".orig.tar.gz "data/"
debuild -us -uc
popd
