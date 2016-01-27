api gateway config
==================

This directory contains the default config for the API Gateway certified to work with the current cell-os.

## Directory structure

### conf.d
TBD

### environment.conf.d
TBD

### html
TBD

### tests
TBD

### scripts
TBD

## Executing integration tests
The tests are executed via Docker and are a good mean to ensure that the nginx syntax is correct
and that the basic functionality works correctly.

```sh
make test
```

These tests offer support for testing the lua scripts created in `api-gateway-config/tests`.
Integration testing with other components such as Mesos, Marathon are not in the scope.

