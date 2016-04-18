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
| cell-os-base-1.2.1-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.2.1-SNAPSHOT.json) | All regions available. Access through `.metal-cell.adobe.io` gateway endpoints. [docs](docs/aws-button.md)|
| cell-os-base-1.2.0 | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.2.0.json) | All regions available. Access through `.metal-cell.adobe.io` gateway endpoints. [docs](docs/aws-button.md)|
| cell-os-base-1.1-rc1 | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.1-rc1.json) | All regions available. Access through bastion / socks proxy|
| cell-os-base-1.0-SNAPSHOT | AWS           | us-west-2     | [![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-os-us-west-2&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.0-SNAPSHOT.json) | All regions available. Access through bastion / socks proxy|
| cell-os-base-1.0-SNAPSHOT | Vagrant       | your laptop   | [Amoeba](https://git.corp.adobe.com/metal-cell/amoeba) ||
| cell-os-base-1.0-SNAPSHOT | vanilla / DIY | *             | [existing clusters](https://git.corp.adobe.com/metal-cell/clusters)    ||
| cell-os-base-1.0-SNAPSHOT | CMDB          | TBD           | TBD ||


# CLI

    ./cell create cell-1
    ./cell list cell-1
    ./cell scale cell-1 body 200
    ./cell ssh cell-1 body

Details, caveats, TODOs in the [aws deployment section](deploy/aws/README.md).
Currently only AWS is supported by the CLI.


## Install

#### **Step 0**: Configure [AWS CLI](http://aws.amazon.com/cli/)
The cell CLI tool is using a bunch of Python packages, that talk to AWS:

    aws configure

> NOTE  
You will need an [acccess key id and secret access key](http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html) for this. 
Contact your account manager if you don't have one.

**We recommend using [virtualenv](http://virtualenv.readthedocs.org/en/latest/)**

#### **Step 1**: Running from source

Install `requirements.txt` dependencies

    cd git-repo/cell-os
    pip install -r requirements.txt
    ./cell

#### **Step 1**: pip package (new feature*)

    pip install --upgrade git+ssh://git.corp.adobe.com/metal-cell/cell-os.git
    cell --help

 \* We've recently added the pip functionality and has so far worked well. If you have any issues
please report them promptly. 

#### **Step 2**: Activate virtualenv (both source and pip)

    virtualenv env
    source env/bin/activate

## Usage

    export AWS_KEY_PAIR=<the EC2 keypair that should be used. Defaults to first key on the AWS account>
    export KEYPATH=<the location of your ${AWS_KEY_PAIR}.pem (must end in .pem).defaults to ~/.ssh>

Create a new cell
    
    ./cell create cell-1

Delete an existing cell

    ./cell delete cell-1

# CellOS version bundle

The cell-os version bundle captures the necessary module versions that are developed,
tested, and certified to work together.

[cell-os-base](cell-os-base.yaml)

# Documentation

* [Command Line Interface](docs/cli.md)
* [Cell-OS Deployment Implementation](docs/deployment-implementation.md)
* [AWS Deployment](docs/deployment-aws.md)
* [Builds and Packaging](docs/packaging.md)
* [User Guide](docs/userguide.md)
* [Developer's Guide](docs/development.md)
