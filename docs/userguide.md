# Running and deploying on CellOS

# Cell resources available for users on startup

* S3 bucket: `s3://cell-os--CELLNAME/cell-os--CELLNAME`
    * Writable dirs are: `s3://cell-os--CELLNAME/cell-os--CELLNAME/shared/http`
* Marathon, Mesos endpoints (see below)
    * Mesos roles: by default all machines in a certain role are tagged with an attribute called `role`, and the value of that cell subdivision (`stateless-body`, `stateful-body`, `membrane`)
* HDFS
* Gateway URLS

# Cell service discovery

Cellos uses Adobe.io gateway for service discovery.
An empty cell exposes at least a set of urls that can be used to get configuration from:

* `http://zookeeper.gw.CELLNAME.metal-cell.adobe.io` - endpoint for Exhibitor / Zookeeper
* `http://mesos.gw.CELLNAME.metal-cell.adobe.io` - endpoint for Mesos (see running frameworks and tasks, active mesos slaves, get information on running tasks)
* `http://marathon.gw.CELLNAME.metal-cell.adobe.io` - endpoint for Marathon (POST to it so long-running workloads start on Mesos, see list of running apps, etc)
* `http://hdfs.gw.CELLNAME.metal-cell.adobe.io` - active HDFS namenode (see information on HDFS capacity, etc)
    * `http://hdfs.gw.CELLNAME.metal-cell.adobe.io.conf`, `http://hdfs.gw.CELLNAME.metal-cell.adobe.io/conf?format=json` - useful endpoint to use in HDFS clients (dumps running HDFS configuration)

## Workload discovery

User workloads are discovered in the same way; 
An user application `APP`, running on Marathon, will be available at `http://app.gw.CELLNAME.metal-cell.adobe.io`

By default, all exposed ports and hosts in Marathon will be created as a load-balanced upstream configuration for Gateway. 
This means that hitting `http://app.gw.CELLNAME.metal-cell.adobe.io` will hit all exposed ports and hosts in a round-robin fashion.

> The endpoints described are available only from a set of specified egress IPS.
> Currently, this includes all Adobe egress IPs.

# Running workloads on Marathon/Mesos

Please see upstream Marathon documentation: [Application Basics](https://mesosphere.github.io/marathon/docs/application-basics.html)
To run a Mesos framework (which is in itself a long-running program), users can start them in Marathon

## Scheduling to specific cell subdivisions

Each subdivision's is available through the Mesos `role` attribute:
To set a [Marathon constraint](https://github.com/mesosphere/marathon/blob/master/docs/docs/constraints.md)
to run in the stateless body you can:

    "constraints": [["role", "CLUSTER", "stateless-body"]]

> Public workloads need to be scheduled on the `membrane` role

# HTTP access to S3 folder

Applications that need remote configuration, can upload files to `s3://cell-os--CELLNAME/cell-os--CELLNAME/shared/http`. The folder can be accessed from inside cell's VPC. 

> **Note:** This folder should only contain information that is shareable between workloads.
> 
> **Example:** A `.dockercfg` might be needed in order to get docker images from private registries. This file could be uploaded in this folder and accessed using HTTP.
