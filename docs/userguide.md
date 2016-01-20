# Running on CellOS

# Service are available trough the cell gateway
Services are not exposed directly externally

# Scheduling to specific cell subdivisions

Each subdivision's is available through the Mesos `role` attribute:
To set a [Marathon constraint](https://github.com/mesosphere/marathon/blob/master/docs/docs/constraints.md)
to run in the stateless body you can:

    "constraints": [["role", "CLUSTER", "stateless-body"]]

# HTTP access to S3 folder
Applications that need remote configuration, can upload files to `s3://bucket/shared/http`. The folder can be accessed from inside cell's VPC. 

> **Note:** This folder should only contain information that is shareable between workloads.
> 
> **Example:** A `.dockercfg` might be needed in order to get docker images from private registries. This file could be uploaded in this folder and accessed using HTTP.