#!/bin/sh

# fail if one command fails
set -e

# install requirements
pip install --no-cache-dir -r requirements_dev.txt

# run tests in the context of the tests dir
retdir=$(pwd)
cd /opt/resource-tests

# test
pylama -o ${retdir}/setup.cfg /opt/resource /opt/resource-tests/
py.test -l --tb=short -r fE /opt/resource-tests

# return to previous location
cd ${retdir}

# cleanup
rm -fr /tmp/*
pip uninstall -y -r requirements_dev.txt