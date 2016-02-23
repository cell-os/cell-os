# Intro

This userguide assumes you have a working cell.

To create a cell see the [cli instalation](https://git.corp.adobe.com/metal-cell/cell-os#install) the [cli documentation](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/docs/cli.md)

TLDR: 

    ./cell create my-new-cell

For convenience 

    export $CELL_NAME=my-new-cell

# Cell resources available for users on startup:

    ./cell list $CELL_NAME 

## Core services

Started automatically with the cell:

*  api-gateway / load balancer (available under `*.gw.$CELL_NAME.metal-cell.adobe.io` DNS)
* `http://zookeeper.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://mesos.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://marathon.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://hdfs.gw.$CELL_NAME.metal-cell.adobe.io`

Not started automatically (yet) but deployable through the cell cli as [DCOS packages](https://git.corp.adobe.com/metal-cell/cell-universe)

* Kafka
* HBase 
* OpenTSDB

## S3 Bucket
Each cell has an associated bucket with several subdirectories.  
By default this will be:

    s3://cell-os--$CELL_NAME/cell-os--$CELL_NAME

For more info see [HTTP access to S3 folder](#HTTP-access-to-S3-folder)

**The endpoints described are available only from a restricted set of egress IPS**

# Running Workloads

## CellOS Services

CellOS comes with a [DCOS repository](https://git.corp.adobe.com/metal-cell/cell-universe) that you can use 

    $ ./cell dcos $CELL_NAME package update
    
    $ ./cell dcos $CELL_NAME package list
    Running dcos package list...
    NAME        VERSION  APP     COMMAND     DESCRIPTION
    kafka       0.9.4.0  /kafka  kafka       Apache Kafka running on top of Apache Mesos

To run an existing service [packaging/services section](packaging.md#core-cellos-services).

TLDR - it's typically something like:

    $ ./cell dcos $CELL_NAME package install ...

## Running your own workloads

To get started you can run a simple docker container by:

```
$ curl -X POST -H "Content-Type: application/json" \
-d '
{
  "id": "hello-cellos",
  "cmd": "python -m SimpleHTTPServer $PORT", 
  "mem": 50, 
  "cpus": 0.1, 
  "instances": 1
}' \
http://marathon.gw.$CELL_NAME.metal-cell.adobe.io/v2/apps
```

Now if you open `http://hello-cellos.gw.$CELL_NAME.metal-cell.adobe.io` in a browser you should see the server running.

> **Pro tip**
> install [httpie](https://github.com/jkbrzt/httpie) using your package manager (brew, apt, yum, pip):
```    
brew install httpie
```
> try
```
`http http://marathon.gw.$CELL_NAME.metal-cell.adobe.io/v2/tasks Accept:text/plain`
```

## DCOS Packages

See the [packaging](packaging.md) documentation for more details.

It's easy to run applications with Marathon, however most times your service will depend on other services (like Kafka) as well as expose its own configuration handles.

You can do this by generating Marathon templates, versioning them and making them available in a repo.

DCOS packages are a convenient way (simply JSON) to package and distribute your service. 
They simply specify a Marathon JSON template together with some metadata that allows you to configure a service. 

See [cell universe](https://git.corp.adobe.com/metal-cell/cell-universe) for existing CellOS DCOS packages.  

Marathon documentation: [Application Basics](https://mesosphere.github.io/marathon/docs/application-basics.html)

## Scheduling to specific cell subdivisions

If you want your workload to run only on `stateful-body` or only on `membrane` you can restrict it
trough [marathon constraints](https://github.com/mesosphere/marathon/blob/master/docs/docs/constraints.md).

Each subdivision's role is available through the Mesos `role` attribute:

To run in the stateless body you can:

    "constraints": [["role", "CLUSTER", "stateless-body"]]

# Private Docker Registry Authentication

You can use the shared http "folder" in S3 to store these (see the section on S3 access).
Any http accessible .dockercfg archive would work.


# Service and Configuration Discovery 

A service with named `foo-service` running in cell named `bar-cell` can be located through the cell load balancer at:

```
foo-service.gw.bar-cell.metal-cell.adobe.io
```

Optionally, if the service exposes additional **configuration** this can be retrieved from

```
foo-service.gw.bar-cell.metal-cell.adobe.io/cellos/config
```

E.g. 

```
http://kafka.gw.c1.metal-cell.adobe.io/cellos/config

{
  brokers: [
    "ip-10-0-0-105.us-west-1.compute.internal:31000"
  ]
}
```

## How service discovery works

Each cell runs a distributed [Adobe.io apigateway](https://github.com/adobe-apiplatform/apigateway) service
used to perform service discovery and load balancing.

The current load balancing implementation polls the `/v2/tasks` marathon endpoint every few seconds and will use that to expose each service:

* marathon app `id` will be used as service discriminator
* marathon tasks are used to extract `host`, `ports[0]` for each task and used as endpoints to forward requests (round-robin)

Any service deployed in Marathon is discoverable through the above scheme by default.

## Configuring discovery for a new service

You can use [Marathon labels (`"labels": {}`)](https://github.com/mesosphere/marathon/blob/master/examples/labels.json) to control the load balancer behavior: 

* `lb:enabled` - enables or disables proxying functionality for this service; Default is *true*;
* `lb:ports` - Indexes of ports to forward to;
  * ~~all ports will be created as a load-balanced upstream configuration for Gateway~~
  * currently only first port (`$PORT0`) is exposed.
* `lb:module` - Optional - specifies a custom GW module to handle this application type; the configuration and proxying microservice for this specific application;

# HTTP access to S3 folder

Each cell has an associated bucket along with "folders" that each cell subdivision will have access to, plus a `shared` "folder" which is accessible from all cell subdivisions.
The `shared/http` "folder" can be accessed over HTTP directly form inside the VPC.

Applications that need remote configuration, can upload files to `s3://cell-os--$CELL_NAME/cell-os--$CELL_NAME/shared/http`. The folder can be accessed from inside cell's VPC. 

> **Note:** This folder should only contain information that is shareable between workloads.
> 
> **Example:** A `.dockercfg` might be needed in order to get docker images from private registries. This file could be uploaded in this folder and accessed using HTTP.
