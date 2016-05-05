# Intro

This userguide assumes you have a working cell.

To create a cell see the [CLI installation](https://git.corp.adobe.com/metal-cell/cell-os#install)
and the [CLI documentation](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/docs/cli.md)

TLDR: 

    ./cell create my-new-cell

For convenience 

    export $CELL_NAME=my-new-cell

# Cell resources available for users on startup:

    ./cell list $CELL_NAME 

## Core services

Started automatically with the cell:

*  api-gateway / load balancer (available under 
`*.gw.$CELL_NAME.metal-cell.adobe.io` DNS)
* `http://zookeeper.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://mesos.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://marathon.gw.$CELL_NAME.metal-cell.adobe.io`
* `http://hdfs.gw.$CELL_NAME.metal-cell.adobe.io`

Not started automatically (yet), but deployable through the cell CLI as
[DCOS packages](https://git.corp.adobe.com/metal-cell/cell-universe).

* Kafka
* HBase 
* OpenTSDB

## S3 Bucket
Each cell has an associated bucket with several subdirectories.  
By default, the CLI will create the bucket, but pre-existing bucket
can be used as well.

Everything is namespaced under a cell-level directory for this purpose.

    s3://cell-os--$CELL_NAME/cell-os--$CELL_NAME

Under the cell directory each cell body has a corresponding directory to which 
it has exclusive `r/w` access:

* `/nucleus`
* `/stateless-body`
* `/stateful-body`
* `/membrane

In addition there's a shared directory to which all bodies have access to
* `/shared`

For more info see [HTTP access to S3 folder](#http-access-to-S3-folder)

> **NOTE:**  
The endpoints described are available only from a restricted set of egress IPS**

### Namespacing user-level workloads in S3
We don't currently enforce finer grained accees to S3 resources.
However, we recommend that user-level workloads namespace their S3 resources under

    /users/<tenant>/<subnamespaces>`

This will allow us to further isolate access between tenants of the same cell and 
within namespaces of the same tenant.

# Running Workloads

## CellOS Services

CellOS comes with a 
[DCOS repository](https://git.corp.adobe.com/metal-cell/cell-universe) that you
can use:

    $ ./cell dcos $CELL_NAME package update
    
    $ ./cell dcos $CELL_NAME package list
    Running dcos package list...
    NAME        VERSION  APP     COMMAND     DESCRIPTION
    kafka       0.9.4.0  /kafka  kafka       Apache Kafka running

To run an existing service 
[packaging/services section](packaging.md#core-cellos-services).

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

Now if you open `http://hello-cellos.gw.$CELL_NAME.metal-cell.adobe.io` 
in a browser you should see the server running.

> **Pro tip**
> install [httpie](https://github.com/jkbrzt/httpie) using your package 
manager (brew, apt, yum, pip):
```    
brew install httpie
```
> try
```
`http http://marathon.gw.$CELL_NAME.metal-cell.adobe.io/v2/tasks Accept:text/plain`
```


#### Port Ranges
In cell's body workloads may use any port between `8081-32000`. 
It is recommended to work with dynamic ports which are auto-assigned by Mesos 
or its frameworks and let the api-gateway / load balancer to automatically 
discover and expose them. 

> **NOTE**:  
For more information on Marathon ports 
[read this page](https://mesosphere.github.io/marathon/docs/ports.html).


## DCOS Packages

See the [packaging](packaging.md) documentation for more details.

It's easy to run applications with Marathon, however most times your service 
will depend on other services (like Kafka) as well as expose its own 
configuration handles.

You can do this by generating Marathon templates, versioning them and making 
them available in a repo.

DCOS packages are a convenient way (simply JSON) to package and distribute your
service. 
They simply specify a Marathon JSON template together with some metadata that 
allows you to configure a service. 

See [cell universe](https://git.corp.adobe.com/metal-cell/cell-universe) for 
existing CellOS DCOS packages.  

Marathon documentation: 
[Application Basics](https://mesosphere.github.io/marathon/docs/application-basics.html)

## Scheduling to specific cell subdivisions

If you want your workload to run only on `stateful-body` or only on `membrane`
you can restrict it trough 
[marathon constraints](https://github.com/mesosphere/marathon/blob/master/docs/docs/constraints.md).

Each subdivision's role is available through the Mesos `role` attribute:

To run in the stateless body you can:

    "constraints": [["role", "CLUSTER", "stateless-body"]]

# Private Docker Registry Authentication

You can use the shared http "folder" in S3 to store these (see the section on 
S3 access). Any http accessible .dockercfg archive would work.

# Service and Configuration Discovery 

A service with named `foo-service` running in cell named `bar-cell` can be 
located through the cell load balancer at:

```
foo-service.gw.bar-cell.metal-cell.adobe.io
```

Optionally, if the service exposes additional **configuration** this can be 
retrieved from

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

Each cell runs a distributed 
[Adobe.io apigateway](https://github.com/adobe-apiplatform/apigateway) service
used to perform service discovery and load balancing.

The current load balancing implementation polls the `/v2/tasks` marathon 
endpoint every few seconds and will use that to expose each service:

* marathon app `id` will be used as service discriminator
* marathon tasks are used to extract `host`, `ports[0]` for each task and used
as endpoints to forward requests (round-robin)

Any service deployed in Marathon is discoverable through the above scheme by 
default.

## Configuring discovery for a new service

You can use 
[Marathon labels (`"labels": {}`)](https://github.com/mesosphere/marathon/blob/master/examples/labels.json)
to control the load balancer behavior: 

* `lb:enabled` - enables or disables proxying functionality for this service; 
Default is *true*;
* `lb:ports` - Indexes of ports to forward to
  * currently only first port (`$PORT0`) is exposed.
* `lb:module` - Optional - specifies a custom GW module to handle this 
application type; the configuration and proxying microservice for this 
specific application;

## Service discovery and load balancing != api management

There's a full set of features enabled by the Adobe.io api-gateway api 
management layer. 
While there may be a subset of overlapping functionality there, we should 
strive to keep the separation of concerns, so learn how that works before 
trying to do something related to that with this.

# Access

Each cell is isolated and access is available through:

* cell load balancer (gateway)
* ssh (`./cell ssh` command)
* direct http through SOCKS5 proxy (`./cell proxy` command, browser settings)

By default all access is restricted to a set of whitelisted networks which are
provided through:

* a JSON downloaded from `net_whitelist_url`
* a local configuration file in the code `deploy/config/net-whitelist.json`

The *first* of these 2 locations which exists will yield the list of accepted networks which can access a cell.

```json
{
  "networks": [
    {
      "net_address": "127.127.16.0",
      "net_address_type": "ipv4",
      "net_mask": 23
    }
  ]
}
```

## SSH

When creating the cell a dedicated keypair and a local private `.pem` are
generated. The private key is placed in:

    .generated/<cell-name>/cell-os--<cell-name>.pem

Existing or new keys can be used (imported) by placing them in this location. You
cannot access a cell without first importing the creator's key in this location.

> **NOTE**: 
Before 1.2.1 keys were in the default `~/.ssh/cell-os--<cell-name>.pem` or
provided through environment variables. There's a migration mechanism in place,
that copies the keys from the old location to the new one.

There's currently no mechanism to automatically add new keys, although if created
and imported under the cell local config folder, they should work.

## Proxy 

There's no direct HTTP access to services running in the cell.
All access happens through the load balancer.

Internal hostnames such as `ip-x-y-z-t.internal` cannot typically be resolved
through DNS. To access services that expose private hostnames in their UIs you can
use a SOCKS proxy. 

    ./cell proxy <cell-name>

This creates a SOCKS5 proxy on `localhost:1234` (configurable) in the background.
You can configure your browser with a proxy plug-in like 
[Proxy SwitchyOmega](https://chrome.google.com/webstore/search/switchy%20omega)
or FoxyProxy and route all internal IPs through the SOCKS proxy. 

## S3

### HTTP access to S3 folder
The `shared/http` "folder" can be accessed over HTTP directly form inside the VPC.

Applications that need remote configuration, can upload files to 
`s3://cell-os--$CELL_NAME/cell-os--$CELL_NAME/shared/http`.  
The folder can be accessed from inside cell's VPC as
`"https://cell-os--$CELL_NAME.s3.amazonaws.com/cell-os--$CELL_NAME/shared/http"`

> **NOTE:** 
This folder should only contain information that is shareable between workloads.
E.g. a `.dockercfg` might be needed in order to get docker images from private 
registries. This file could be uploaded in this folder and accessed using HTTP.

## Docker private registries in Marathon
For more information on how to package docker credentials for Marathon:
https://mesosphere.github.io/marathon/docs/native-docker-private-registry.html

Once you packaged them you can upload and use them as described in the S3 HTTP
section.

# Configuration

For all cli options and configurations run `./cell --help`.  
`~/.cellos/config` can be used for general cli settings (e.g. default region).  

The typical configuration override order is:

1. file
2. environment
3. argument

Hence, the cli arguments have the highest priority.  

Cell level caches, metadata and configurations are stored in `.generated`. 
See the CLI advanced section on [.generated](userguide.md#generated) for 
more information.
