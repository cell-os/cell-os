## Cell-OS base deployment packages

TODO

## Useful base Docker images

Docker is the most usual packaging mechanism for Cell-OS. 
Our recommended base images are all based on Alpine Linux and optimized for size. 

> Note: Alpine Linux will become the default base image for Docker.

Some useful base images to start for your workloads: 

* [docker-alpine](https://github.com/gliderlabs/docker-alpine)
    * Beware of some issues with DNS resolving from `resolv.conf`
    * Should be fixed with `alpine:3.4`
* [sillelien-alpine](https://github.com/sillelien/base-alpine)
    * docker-alpine with java and dns hacks (using dnsmasq and the S6 process supervisor)
    * a good starting point, we need to remove tutum specific things from it
* [sillelien-alpine-glibc](https://github.com/sillelien/base-alpine-glibc)
    * on top of the previous image, also adds glibc
* [docker-alpine-jdk8](https://github.com/frol/docker-alpine-oraclejdk8)
    * base alpine image with Oracle JDK 8 (which we should standardize for production workloads)
* [docker-alpine-java](https://github.com/anapsix/docker-alpine-java)
    * another version for a Java one. 

Some useful tools/documentation for Docker images: 

* [Atlassian: Minimal Java Docker Containers](https://developer.atlassian.com/blog/2015/08/minimal-java-docker-containers/)
* [Docker Image Size Comparison](https://www.brianchristner.io/docker-image-base-os-size-comparison/)
* [imagelayers.io](https://imagelayers.io/) - very useful tool to compare images and get size information for each layer

## Cell-OS DCOS packages

Cell-OS can use DCOS packages. 

* DCOS packages are basically Mesos/Marathon workloads available in a [public repository](https://github.com/mesosphere/universe/)
* Operator has a [dcos-cli tool](https://github.com/mesosphere/dcos-cli/)
* We provide our [own package repository](http://git.corp.adobe.com/metal-cell/cell-universe) (the tool can use more than one)

Some DCOS packages rely on some magic parameters being set by the DCOS environment (this part will get better as the open-source version will get fleshed out).  

Because of this, we need to have a customization layer for DCOS packages where we inject Cell-OS parameters (Basically, Zookeeper quorum, Mesos and Marathon URLs).

This customization layer is embedded in the default values in the `config.json`. The cell-os DCOS wrapper takes these values and generates a template file which we then render json options of.

```json
...
"hdfs-namenode-endpoint": {
    "type": "string",
    "description": "HDFS namenode host URL",
    "default": "hdfs.gw.{{cell}}.metal-cell.adobe.io"
},
...
```

When running the Cell-OS DCOS wrapper( `./cell dcos...`), we:

* check for the package being installed
* if we have a customization file for it, we
    * render the configuration file for the specific cell
    * modify the DCOS command to add the options that have our customizations: `./cell dcos package install X --options ....`
* if we don't, we run the command as specified; some packages might work, some not
* we are working on a subset of available packages

## Core CellOS Services

```
# cell name variable used only for example purposes
export cell_name=<YOUR-CELL-NAME-HERE>
```

```bash
# create / update dcos package cache
./cell dcos ${cell_name} package update
```

List available packages

```bash
❯ ./cell dcos $cell_name package search
Running dcos package search...
NAME                VERSION  FRAMEWORK  SOURCE                                                                            DESCRIPTION
hbase-master        0.1.0    False      https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-1.2-SNAPSHOT.zip  HBase master workload running on top of Apache Mesos
hbase-regionserver  0.1.0    False      https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-1.2-SNAPSHOT.zip  HBase region-server workload running on top of Apache Mesos
kafka               0.9.4.0  True       https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-1.2-SNAPSHOT.zip  Apache Kafka running on top of Apache Mesos
```

### HBase
HBase is currently deployed as two workloads master and regionserver
```bash
./cell dcos ${cell_name} package install hbase-master
./cell dcos ${cell_name} package install hbase-regionserver
```

> **NOTE**  
This will install using defaults.  
See `dcos package` help on how to set additional configuration.  
Run `./cell dcos ${cell_name} package describe --config hbase-master` 
to see all possible configurations

Check the config endpoint
```
curl http://hbase-master.gw.$cell_name.metal-cell.adobe.io/cellos/config
HTTP/1.1 200 OK
```

```json
{
    "hbase.rootdir": "hdfs://saasbase//hbase-1",
    "hbase.zookeeper.quorum": "10.0.0.77:2181,10.0.0.78:2181,10.0.0.76:2181",
    "zookeeper.znode.parent": "/hbase-1"
}
```

### Kafka

Using the [mesos-kafka scheduler](https://github.com/mesos/kafka). For additional operations please consult the [upstream documentation](https://github.com/mesos/kafka#starting-and-using-1-broker)

```bash
 
# installs the cli package (locally)
./cell dcos ${cell_name} package install --cli kafka
./cell dcos ${cell_name} kafka help

# Install / Run Kafka Mesos framework on Marathon
./cell dcos ${cell_name} package install --app --app-id=kafka kafka
```

> NOTE  
It takes a few seconds after installing the packange until the Kafka scheduler becomes available in the load balancer.
Running the following (`broker add`) too early may yield an HTTP 502 error.
This is a known issue, but a harmless one. You can just retry or check the status of the kafka scheduler (see the dcos-cli documentation on how to query marathon from the CLI)

```bash
# Add a broker
./cell dcos ${cell_name} kafka broker add 0 --cpus 2 --mem 1024 --options "log.dirs=/mnt/data_1/kafka_data/broker0" --constraints "role=like:stateful.*,hostname=unique"
```
* `--options` - note that we're passing the mount point when we add the broker. 
   * We'll later pick this behind the scenes 
* `--constraints` - we want peristent workloads to go only to the stateful part of the cell (stateful-body)
   * also we want to run one broker per node per cluster (nodes from multiple cluster may end up on the same node)

```bash
# Start Broker !!!
./cell dcos ${cell_name} kafka broker start 0
```

### OpenTSDB

OpenTSDB requires a running instance of HBase.  
It will attempt to create its tables at container startup.  
By default it uses the HBase installation rooted in ZK in `/hbase-1`.

See the HBase package documentation for help on how to set it up.

```bash
./cell dcos ${cell_name} package install opentsdb
```

Once provisioned you should be able to access OpenTSDB UI at 
`http://opentsdb.gw.<cell>.metal-cell.adobe.io`

```bash
curl http://opentsdb.gw.${cell_name}.metal-cell.adobe.io/api/version

{"short_revision":"","repo":"/opentsdb-2.2.0","host":"1c7d9aa5eff8","version":"2.2.0","full_revision":"","repo_status":"MODIFIED","user":"root","timestamp":"1456487791"}
```

Navigating to http://hbase-master.gw.YOUR_CELL_NAME.metal-cell.adobe.io/ should show a few `tsdb*` tables. 

> NOTE  
You should now be able to point tcollectors to `opentsdb.gw.${cell_name}.metal-cell.adobe.io` to push data.
Note that this will route all that traffic through the gateway, though. 
We'll likely provide a `/config` endpoint to retrieve the list of tsdb nodes, alternatively you can retrieve them through Marathon. However, note that these may change at runtime.




