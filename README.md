cell-os
=======

![](https://git.corp.adobe.com/metal-cell/scrub/raw/master/cell-os-demo.gif)

`cell-os` is the software distribution for [Metal Cell](https://git.corp.adobe.com/metal-cell/metal-cell)

The cell-os base contains the minimal installation required to run the rest of the sofware.  
It currently consista of Zookeeper, Docker, Mesos and Marathon.

| Version              | Provider      | Region        |       | Notes |
| -------------------- | ------------- |:-------------:| ----- | ----- |
| cell-os-base-1.0-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3-us-west-2.amazonaws.com/cell-os-public/elastic-cell.json) | All regions available. Access through bastion / socks proxy|
| cell-os-base-1.0-SNAPSHOT | Vagrant       | your laptop   | [Amoeba](https://git.corp.adobe.com/metal-cell/amoeba) ||
| cell-os-base-1.0-SNAPSHOT | vanilla / DIY | *             | [existing clusters](https://git.corp.adobe.com/metal-cell/clusters)    ||
| cell-os-base-1.0-SNAPSHOT | CMDB          | TBD           | TBD ||
| cell-os-base-1.1          | GCE           | N/A           | N/A ||
| cell-os-base-1.1          | IT Cloud      | N/A           | N/A ||
| cell-os-base-1.1          | CPT           | N/A           | N/A ||


# CLI

    ./cell create cell-1
    ./cell list cell-1
    ./cell scale cell-1 body 200
    ./cell ssh cell-1 body

Details, caveats, TODOs in the [aws deployment section](deploy/aws/README.md)
Currently only AWS is supported by the CLI.

### Requirements

#### Install and configure [AWS CLI](http://aws.amazon.com/cli/)

    pip install awscli
    aws configure

## Usage

    export AWS_ACCESS_KEY_ID=<your access key id>
    export AWS_SECRET_ACCESS_KEY=<your secret access key>

Create a new cell
    
    ./cell create cell-1


**Go to the AWS Console and accept the CentOS AMI agreement (see https://jira.corp.adobe.com/browse/CELL-58 for details) 
if you haven't done so. The stack will hang creating the autoscaling groups until you do so.**

Delete an existing cell

    ./cell delete cell-1


# CellOS version bundle

The cell-os version bundle captures the necessary module versions that are developed,
tested and certified to work together.

[cell-os-1.0](cell-os-base-1.0-SNAPSHOT.yaml)

# Documentation

* [Command Line Interface](docs/cli.md)
* [cell-os deployment implemenatation](docs/deployment-implementation.md)
* [AWS deployment](deploy/aws/README.md).
