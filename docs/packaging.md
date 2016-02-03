## Cell-OS base deployment packages

## Cell-OS DCOS packages

Cell-OS can use DCOS packages. 

* DCOS packages are basically Mesos/Marathon workloads available in a [public repository](https://github.com/mesosphere/universe/)
* Operator has a [dcos-cli tool](https://github.com/mesosphere/dcos-cli/)
* We provide our [own package repository](http://git.corp.adobe.com/metal-cell/cell-universe) (the tool can use more than one)

Some DCOS packages rely on some magic parameters being set by the DCOS environment (this part will get better as the open-source version will get fleshed out)
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

### Usage 

```bash
# prepare config files
./cell config CELLNAME
# optional step - add a package repository
./cell dcos CELLNAME config append package.sources https://github.com/mesosphere/universe/archive/version-1.x.zip
# create dcos package cache
./cell dcos CELLNAME package update
 # installs the cli package
./cell dcos CELLNAME package install --cli kafka
# Run Kafka Mesos framework on Marathon
./cell dcos CELLNAME package install --app --app-id=kafka kafka
# Add a broker
./cell dcos CELLNAME kafka broker add 0 --cpus 2 --mem 1024 --options "log.dirs=/mnt/data_1/kafka_data/broker0" --constraints "role=like:stateful.*,hostname=unique"
# Start Broker !!!
./cell dcos CELLNAME kafka broker start 0
```
