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
Because of this, we need to have a customization layer for DCOS packages where we inject Cell-OS parameters (Basically, Zookeeper quorum, Mesos and Marathon URLs)

```json
{
    "mesos": {
        "master": "zk://{{zk}}/mesos"
    }, 
    "kafka": {
        "app": {
            "cpus": 2, 
            "mem": 512, 
            "heap-mb": 512,
            "instances": 1
        }, 
        "zk": "{{zk}}"
    }
}
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

### Kafka

Using the [mesos-kafka scheduler](https://github.com/mesos/kafka). For additional operations please consult the [upstream documentation](https://github.com/mesos/kafka#starting-and-using-1-broker)

```bash
 
# installs the cli package (locally)
./cell dcos ${cell_name} package install --cli kafka
./cell dcos ${cell_name} kafka help

# Install / Run Kafka Mesos framework on Marathon
./cell dcos ${cell_name} package install --app --app-id=kafka kafka
```

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
