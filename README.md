```
 ██████╗███████╗██╗     ██╗             ██████╗  ███████╗     ██╗    ██████╗ 
██╔════╝██╔════╝██║     ██║            ██╔═══██╗ ██╔════╝    ███║    ╚════██╗
██║     █████╗  ██║     ██║     █████╗ ██║   ██║ ███████╗    ╚██║     █████╔╝
██║     ██╔══╝  ██║     ██║     ╚════╝ ██║   ██║ ╚════██║     ██║    ██╔═══╝ 
╚██████╗███████╗███████╗███████╗       ╚██████╔╝ ███████║     ██║██╗ ███████╗
 ╚═════╝╚══════╝╚══════╝╚══════╝        ╚═════╝  ╚══════╝     ╚═╝╚═╝ ╚══════╝
```

![](https://git.corp.adobe.com/metal-cell/scrub/raw/master/cell-os-demo.gif)

`cell-os` is the software distribution for [Metal Cell](https://git.corp.adobe.com/metal-cell/metal-cell)

The cell-os base contains the minimal installation required to run the rest of 
the software. It currently consists of Zookeeper, Docker, Mesos and Marathon, 
HDFS and the api-gateway.
 

| Version              | Provider      | Region        |       | Notes |
| -------------------- | ------------- |:-------------:| ----- | ----- |
| cell-os-base-1.3.0-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.3.0-SNAPSHOT.json) | All regions available. Access through `.metal-cell.adobe.io` gateway endpoints. [docs](docs/aws-button.md)|
| cell-os-base-1.3.0-SNAPSHOT | Azure           | *     |  | [PR](https://git.corp.adobe.com/metal-cell/cell-os/pull/259)
| cell-os-base-1.3.0-SNAPSHOT | Vagrant       | your laptop   | [Amoeba](https://git.corp.adobe.com/metal-cell/amoeba) ||
| cell-os-base-1.2.0 | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.2.0.json) | All regions available. Access through `.metal-cell.adobe.io` gateway endpoints. [docs](docs/aws-button.md)|
| * | vanilla / DIY | *             | [existing clusters](https://git.corp.adobe.com/metal-cell/clusters)    ||


# CLI

    ./cell create cell-1
    ./cell list cell-1
    ./cell scale cell-1 body 200
    ./cell ssh cell-1 body

Details, caveats, TODOs in the [aws deployment section](deploy/aws/README.md).
Currently only AWS is supported by the CLI.

## Run using docker

    docker run -it docker-cell-os.dr.corp.adobe.com/cellos
    
More in the [CLI doc](docs/cli.md#docker)

## Install

    pip install --upgrade git+ssh://git.corp.adobe.com/metal-cell/cell-os.git

More in the [CLI doc](docs/cli.md#classic) 

## Usage

Create a new cell
    
    ./cell create cell-1

Delete an existing cell

    ./cell delete cell-1

# Documentation
* [User Guide](docs/userguide.md)
* [Command Line Interface](docs/cli.md)
* [Cell-OS Deployment Implementation](docs/deployment-implementation.md)
* [AWS Deployment](docs/deployment-aws.md)
* [Builds and Packaging](docs/packaging.md)
* [Developer's Guide](docs/development.md)
