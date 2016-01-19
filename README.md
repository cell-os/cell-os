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

The cell-os base contains the minimal installation required to run the rest of the software.
It currently consists of Zookeeper, Docker, Mesos and Marathon.

| Version              | Provider      | Region        |       | Notes |
| -------------------- | ------------- |:-------------:| ----- | ----- |
| cell-os-base-1.2-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.2-SNAPSHOT.json) | All regions available. Access through bastion / socks proxy|
| cell-os-base-1.1-rc1 | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.1-rc1.json) | All regions available. Access through bastion / socks proxy|
| cell-os-base-1.0-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.0-SNAPSHOT.json) | All regions available. Access through bastion / socks proxy|
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

The cell cli tools use a bunch of Python packages, that talk to AWS. 

    pip install -r requirements.txt

#### Configure [AWS CLI](http://aws.amazon.com/cli/)

    pip install awscli
    aws configure

#### Install `watch`
 With [Homebrew](http://brew.sh/) installed: `brew install watch`
 
 With [ports](http://www.macports.org/) installed: `sudo port install watch`

## Usage

    export AWS_KEY_PAIR=<the EC2 keypair that should be used. Defaults to first key on the AWS account>
    export KEYPATH=<the location of your ${AWS_KEY_PAIR}.pem (must end in .pem).defaults to ~/.ssh>

Create a new cell
    
    ./cell create cell-1

Delete an existing cell

    ./cell delete cell-1

# CellOS version bundle

The cell-os version bundle captures the necessary module versions that are developed,
tested and certified to work together.

[cell-os-1.0](cell-os-base-1.0-SNAPSHOT.yaml)

# Documentation

* [Command Line Interface](docs/cli.md)
* [cell-os deployment implementation](docs/deployment-implementation.md)
* [AWS deployment](deploy/aws/README.md)
* [Builds and Packaging](docs/packaging.md)
