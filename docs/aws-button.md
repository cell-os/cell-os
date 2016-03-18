# Intro
CellOS can be deployed using just the CloudFormation URL 
[![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/new?stackName=cell-1&templateURL=https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-1.2.1-SNAPSHOT.json)

# Requirements
You'll need at least:
* An AWS account
* An existing S3 bucket
* An EC2 keypair (and local `.pem` file) to connect to the instances

# Configuration
For best experience make sure you configure the stack metadata consistent
with the defaults. This will help you avoid some manual configuration later.

Configure the following stack parameters: 

    Stack name=<cell-name>
    BucketName=<cell-name>
    CellName=<cell-name>
    KeyName=<cell-name>
You can find saasbase-deployment keys 
[here](http://saasbase.corp.adobe.com/ops/operations/deployment.html)

Set tags the following tags (in the second CloudFormation screen):

    name=<cell-name>
    version=<cell-os-version e.g. 1.3.0>

You'll then see the progress in the CloudFormation console / Events.

Once the cell is done you'll be able to access services through the 
cell load balancer at

http://mesos.gw.<cell-name>.metal-cell.adobe.io

Similar URLs should work fo for marathon, zookeeper, hdfs, etc.

# CLI 

`./cell` commands should work, once you copy the `.pem` coresponding
to the ec2 keypair us used in 

    <cell-home>/.generated/<cell-name>/cell-os--<cell-name>.pem


