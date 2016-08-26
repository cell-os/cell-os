## Cell-OS base deployment packages

### HDFS

Deployed in nucleus (NameNode) and `stateful-body` (DataNode) at cell creation
time.
Uses `/deploy/seed/10-hdfs-raw` seed which wraps a hadoop2 puppet module.

Once the cell is fully provision you can access the configuration discovery
endpoint at

    http://hdfs.gw.$cell_name.metal-cell.adobe.io/cellos/config

You can get `hdfs-site.xml` (and `core-site.xml`):

    http://hdfs.gw.$cell_name.metal-cell.adobe.io/cellos/config/hdfs-site.xml

#### Using the HDFS WebHDFS REST endpoint

We configure HDFS to also start the WebHDFS rest endpoint for easier access to 
HDFS through HTTP.

**Resources**
* [Official documentation](https://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-hdfs/WebHDFS.html)

Creating a directory in HDFS:
```
$ curl -i -X PUT "http://hdfs.gw.c1.metal-cell.adobe.io/webhdfs/v1/my/dir/to/create?op=MKDIRS&permissions=0755&doas=hadoop&user.name=root"

HTTP/1.1 200 OK
...
Content-Length: 16
Age: 0

{"boolean":true} 
```

Creating a new file inside a directory:
```
$ curl -i -X PUT -T testfile "http://hdfs.gw.c1.metal-cell.adobe.io/webhdfs/v1/my/dir/to/create/testfile?op=CREATE&overwrite=true&permissions=0755&doas=hadoop&user.name=root"

HTTP/1.1 200 OK
...
Content-Length: 16
Age: 0

{"boolean":true} 
```

Download a file:
```
$ curl -i -X GET "http://hdfs.gw.c1.metal-cell.adobe.io/webhdfs/v1/my/dir/to/create/testfile?op=OPEN&doas=hadoop&user.name=root"

HTTP/1.1 200 OK
...
Content-Length: 14

one
two
three
```

## Cell-OS DCOS packages

Cell-OS can use DCOS packages. 

* DCOS packages are basically Mesos/Marathon workloads available in a 
[public repository](https://github.com/mesosphere/universe/)
* Operator has a [dcos-cli tool](https://github.com/mesosphere/dcos-cli/)
* We provide our 
[own package repository](http://git.corp.adobe.com/metal-cell/cell-universe) 
(the tool can use more than one)

Some DCOS packages rely on some magic parameters being set by the DCOS 
environment (this part will get better as the open-source version will get 
fleshed out).  

Because of this, we need to have a customization layer for DCOS packages where 
we inject Cell-OS parameters (Basically, Zookeeper quorum, Mesos and Marathon 
URLs).

This customization layer is embedded in the default values in the `config.json`.
The cell-os DCOS wrapper takes these values and generates a template file which 
we then render json options of.

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
    * modify the DCOS command to add the options that have our customizations: 
    `./cell dcos package install X --options ....`
* if we don't, we run the command as specified; some packages might work, some
 not
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

Optionally, but recommended, you can deploy HBase REST endpoint as well:
```bash
./cell dcos ${cell_name} package install hbase-rest
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

#### Using the HBase REST endpoint
**Resources**
* [Official HBase Book REST chapter](http://hbase.apache.org/book.html#_rest) 
(very slow load in Chrome)
* [Official documentation](https://hbase.apache.org/apidocs/org/apache/hadoop/hbase/rest/package-summary.html)

Get the HBase meta table (`hbase:meta`) schema:

```
❯ http hbase-rest.gw.c1.metal-cell.adobe.io/hbase:meta/schema
HTTP/1.1 200 OK

{ NAME=> 'hbase:meta', IS_META => 'true', coprocessor$1 => 
'|org.apache.hadoop.hbase.coprocessor.MultiRowMutationEndpoint|536870911|', 
COLUMNS => [ { NAME => 'info', BLOOMFILTER => 'NONE', VERSIONS => '10',
IN_MEMORY => 'true', KEEP_DELETED_CELLS => 'FALSE', DATA_BLOCK_ENCODING => 
'NONE', TTL => '2147483647', COMPRESSION => 'NONE', CACHE_DATA_IN_L1 => 'true',
MIN_VERSIONS => '0', BLOCKCACHE => 'true', BLOCKSIZE => '8192', 
REPLICATION_SCOPE => '0' } ] }
```

Create a table named `t1` with a column family named `f1`:
```
curl -v -X PUT \
  http://hbase-rest.gw.c1.metal-cell.adobe.io/t1/schema \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"ColumnSchema":[{"name":"f1", "BLOOMFILTER": "ROW", "VERSIONS":"1", \
  "COMPRESSION": "LZO"}]}'
```

> **NOTE:**:  
The `ColumnSchema` entries must: 
* use lowercase key for the `name` for the column family name or an error will 
be thrown
* use upper case keys for all other properties (e.g. `VERSIONS`) or otherwise
these will not be set and have the upper case entry with the default values.

Delete a table
```
curl -v -X DELETE http://hbase-rest.gw.c1.metal-cell.adobe.io/tsdb/schema
```

### Kafka

Using the [mesos-kafka scheduler](https://github.com/mesos/kafka). For 
additional operations please consult the 
[upstream documentation](https://github.com/mesos/kafka#starting-and-using-1-broker)

```bash
 
# installs the cli package (locally)
./cell dcos ${cell_name} package install --cli kafka
./cell dcos ${cell_name} kafka help

# Install / Run Kafka Mesos framework on Marathon
./cell dcos ${cell_name} package install --app --app-id=kafka kafka
```

> NOTE  
It takes a few seconds after installing the package until the Kafka scheduler 
becomes available in the load balancer. Running the following (`broker add`) 
too early may yield an HTTP 502 error. This is a known issue, but a harmless 
one. You can just retry or check the status of the kafka scheduler (see the 
dcos-cli documentation on how to query marathon from the CLI).

```bash
# Add a broker
./cell dcos ${cell_name} kafka broker add 0 --cpus 2 --mem 1024 --options "log.dirs=/mnt/data_1/kafka_data/broker0" --constraints "role=like:stateful.*,hostname=unique"
```
* `--options` - note that we're passing the mount point when we add the broker. 
   * We'll later pick this behind the scenes 
* `--constraints` - we want persistent workloads to go only to the stateful part
 of the cell (stateful-body)
   * also we want to run one broker per node per cluster (nodes from multiple 
   cluster may end up on the same node)

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
You should now be able to point tcollectors to 
`opentsdb.gw.${cell_name}.metal-cell.adobe.io` to push data.
Note that this will route all that traffic through the gateway, though. 
We'll likely provide a `/config` endpoint to retrieve the list of tsdb nodes, 
alternatively you can retrieve them through Marathon. However, note that these
 may change at runtime.

# Creating New Packages 

> **NOTE:**  
Use of Docker containers or any other containers or DCOS packages is purely
optional. 
Mesos will use a default containerizer and applications can be package as
anything that can be downloaded and expanded in the container sandbox by mesos
such as `tar.gz`.

> **NOTE:**  
We're currently using DCOS as a stop-gap solution. Due to limitations, future
incompatibilities, etc. we may in the future migrate to a different "standard" 
package. 


## Best practices

### Keep the packages self contained
Don't rely on things that *may* be on the mesos agent host (like Java) and make
sure that all dependencies are met.  
Failure to do so may result in undetermined behavior and / or failures later.

### Don't hardcode any configurations in the containers
Your containers need to be portable across cells and other environments.

### Don't store any sensitive information directly in the container
Use secret stores and encryption for that

### Be careful about dependencies lifecycle and configuration binding
Considering a service level dependency like Kafka where you need to configure
the list of brokers to be used for bootstrapping, keep in mind that due to 
failures or other cluster-level or scheduler-level events this may change at
runtime.

Typically all configurations should be retrievable through the standard cellos
config endpoints (`/cellos/config`). 

If you can afford a workload rolling restart you can retrieve the necessary 
information on container startup and you'd only need to configure the workload
name. 

More Details TBD 

## Docker containers

### Build setup
To keep automated build configurations minimal try to contain the build logic
with the container so that you can build and push your container through a 
minimal interface like:

    # build the container
    ./build.sh 
    # release / push the container
    ./release.sh

Consider extracting versions and repositories to variables. For example
`VERSION` - the version of the containerized package
`TAG` - the tag of the container (you can default to the git SHA e.g.
`$(git rev-parse HEAD)` 
`REPO` - the repository (this may also be provided externally (e.g. by Jenkins)
(if you want to release as OSS and don't want to make it too specific).

### Useful base Docker images

Docker is the most usual packaging mechanism for Cell-OS. 
Our recommended base images are all based on Alpine Linux and optimized for 
size and speed.

> Note: Alpine Linux will become the default base image for Docker.

Some useful base images to start for your workloads: 

* [docker-alpine](https://github.com/gliderlabs/docker-alpine)
    * Beware of some issues with DNS resolving from `resolv.conf`
    * Should be fixed with `alpine:3.4`
* [sillelien-alpine](https://github.com/sillelien/base-alpine)
    * docker-alpine with java and dns hacks (using dnsmasq and the
    S6 process supervisor)
    * a good starting point, we need to remove tutum specific things from it
* [sillelien-alpine-glibc](https://github.com/sillelien/base-alpine-glibc)
    * on top of the previous image, also adds glibc
* [docker-alpine-jdk8](https://github.com/frol/docker-alpine-oraclejdk8)
    * base alpine image with Oracle JDK 8 (which we should standardize for 
    production workloads)
* [docker-alpine-java](https://github.com/anapsix/docker-alpine-java)
    * another version for a Java one. 

### Some useful tools/documentation for Docker images: 

* [Atlassian: Minimal Java Docker Containers](https://developer.atlassian.com/blog/2015/08/minimal-java-docker-containers/)
* [Docker Image Size Comparison](https://www.brianchristner.io/docker-image-base-os-size-comparison/)
* [imagelayers.io](https://imagelayers.io/) 
- very useful tool to compare images and get size information for each layer

## DCOS Packages

> **NOTE:**  
We don't yet have a generic template to scaffold this from.
Want to contribute one?

### CellOS specific differences

We treat the `config.json` as a template and replace `{{variables}}` of 
`string` type with cell-level values.


### Testing your modules

Make sure you run 

    $REPO_PATH/scripts/build.sh

You can add a local path to your cell repository:

    ./cell dcos c1 config prepend package.sources \
    "file:///Users/clehene/metal-cell/cell-universe"

> **NOTE:**  
Pay attention to the actual path to avoid headaches from cryptic dcos cli 
errors.  
Make sure you have all 3 slashes in the scheme: `file:///`.  
Make sure to put the root of the repo path.  
If you add garbage to the repo list you can clean it up by editing
`~/.cellos/generated/<cell-name>/dcos.toml`

Run package update

   ./cell dcos c1 package update
   Running dcos package update...
   Updating source [file:///Users/clehene/metal-cell/cell-universe]
   Updating source [https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-1.2.1-SNAPSHOT.zip]


If you get a `ImportError: No module named dcoscli.main` you're likely using
dcos version > 3.6. Make sure your virtualenv is properly sourced so that 
you'll use the right version


Now you can proceed and install the package on a cell

    ./cell dcos c1 package install --yes opentsdb

Use an [existing package](https://git.corp.adobe.com/metal-cell/cell-universe/)
as a template. 

#### Troubleshooting

`package install` returns `Error: Object is not valid`

dcos cli truncates the details of the actual error message.

Enable debugging:

    ./cell dcos c1 --log-level=DEBUG package install --yes marathon

You can generate the marathon json payload :

    ./cell dcos c1 package describe --app --render YOUR_MODULE_NAME

Save it to a file (e.g. `marathon.json`) and POST directly to marathon

    curl -X POST -H "Content-Type: application/json" \
    http://marathon.gw.c1.metal-cell.adobe.io//v2/apps\?force\=true \
    -d@marathon.json  -vvv  

This will return a more detailed erorr message. E.g.

    {
      "message":"Object is not valid",
      "details":[{"path":"/container/docker/image",
      "errors":["must not be empty"]}]
    }
 
### Checklist

1. Read DCOS [contributing a package doc](https://git.corp.adobe.com/metal-cell/cell-universe#contributing-a-package)
1. it goes without saying that you should have solid knowledge and 
understanding about the system you're about to write a package for. 
2. get the package scaffold
   * there's currently no `dcos package generate` 
3. customize package
   * minimal required configurations:
      * name / id 
      * package / container URI and version
3. make sure the package logs properly and the logs can be seen in Mesos 
(we'll automatically capture these)
4. try to let Mesos / Marathon allocate the ports (`$PORT0`, `$PORT1`, etc.),
as this will make scheduling easier.
5. consider writing a Marathon health check so that the service can be restarted
if not working properly
6. Docker container and version should be configurable externally
7. Think about resource use (CPU, RAM) and configure appropriately (e.g. if a 
JVM will need 1GB heap, the container may need 1.2X of that) 
4. bind the config endpoint 
([N/A yet see CELL-334](https://jira.corp.adobe.com/browse/CELL-334)) or write 
a config endpoint plugin 
([example](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/deploy/seed/99-cell/apigateway/api-gateway-config/scripts/lua/service/hbase.lua))

5. document 
   * how to install the package 
   * how to uninstall the package (if needed)
   * how to check if it installed properly (e.g. check an endpoint, or the logs)
   * ([example](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/docs/packaging.md#kafka))
   * config discovery endpoint (/cellos/config) plugin if any

For cell-os packages:
Make a pull-request against [cell-universe repo](https://git.corp.adobe.com/metal-cell/cell-universe)

