# cell-os-base on EC2

The Amazon EC2-based elastic cell consists of a CloudFormation template to provision the
necessary AWS infrastructure for the cell-os base.

# cell-os infrastructure diagram
```
+------------------------------------------------------------------------------+
|          80               80               80               80               |
|   +-------------+   +-------------+   +-------------+   +-------------+      |
|   |    ZK ELB   |   |  Mesos ELB  |   | Marathon ELB|   | Gateway ELB |      |
|   +------+------+   +------+------+   +------+------+   +------+------+      |
|          |                 |                 |                 |             |
| +-----------------------------------------------------+ +-------------------+|
| |        |                 |                 |        | |      |            ||
| |        |        +-------------------------------------------------------+ ||
| |        |        |        |                 |        | |      |          | ||
| | +------+------+ | +------+------+   +------+------+ | | +-------------+ | ||
| | | <--|   |--> | | | <--|   |--> |   | <--|   |--> | | | | <--|   |--> | | ||
| | +-------------+ | +-------------+   +-------------+ | | +-------------+ | ||
| |  Nucleus SG     |    Stateless        Stateful      | | |  Membrane SG  | ||
| |  HDFS NN/QJM    |    Body SG          Body SG       | |                 | ||
| |                 |                     HDFS DN       | |                 | ||
| |                 +-------------------------------------------------------+ ||
| |                            Mesos Agents             | |                   ||
| |                                                     | | +-------------+   ||
| |                                                     | | | <--|   |--> |   ||
| |                                                     | | +-------------+   ||
| |                                                     | |    Bastion SG     ||
| |                                                     | |                   ||
| | Private                                             | | Public            ||
| | Subnet  10.0.0.0/24                                 | | Subnet 10.0.1.0/24||
| +-----------------------------------------------------+ +-------------------+|
+------------------------------------------------------------------------------+
     us+west+2+cell+1  PC   vpc+62c65107 (10.0.0.0/16)         

```

The default cell size is a 3-node nucleus and 1-node stateless body, 1-node 
stateful body, 1-node membrane, 1-node bastion each in separate scaling groups 
(i.e. can be scaled up independently).  

The cell-os-base consists of Zookeeper / Exhibitor, Mesos, Marathon.
cell-os-1.1 extended the base with HDFS (consisting of QJM, NN running in Nucleus and 
DN running in stateful-body).  
All other services typically run on top of the base using one of the cell schedulers.  

> **NOTE:**  
The base module deployment is decoupled from the infrastructure provisioning (AWS specific)

## Internals: How it's made
With cell-os 1.1 we started using [Troposphere](https://github.com/cloudtools/troposphere)
to generate the AWS CF templates.

## Internals: How it works

There's a main CF stack that sets up the VPC along the rest of the 
infrastructure pieces and a multiple nested stacks for individual scaling 
groups which are created by the main stack.

### Main stack: VPC, Subnets, ELBs, Internet Gateway, Routes, Security Groups, etc.

Sets up the infrastructure and creates separate scaling groups for each subdivision
of the cell using nested stacks.

The network is separated in two subnets - a private and a public one, both in
the same AZ.

There's an Internet Gateway and a NAT Gateway.
The private net default route goes to NAT Gateway and the public one to the 
Internet Gateway.  

All nodes except membrane nodes and the bastion are in the private subnet.

Each cell subdivision is created by passing the role, tags, cell modules and
configurations to the nested stack.

Roles and tags are used to identify the EC2 instances and to set attributes.

Each cell has an associated S3 bucket which is divided into directories for each cell 
subdivision (e.g. `s3://<cell-bucket>/<cell-name>/nucleus`). Access is restricted to 
just the corresponding subdivision and is typically read-only. 

In addition there's a shared directory (`/shared`) which can be accessed from all
cell sections. This contains a subdirectory `/shared/http` which can be accessed from
all nodes over HTTP through a 
[VPC Endpoint](http://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/vpc-endpoints.html).


### Cell modules provisioning

Each CF nested stack receives a list of cell modules (called "seeds") to deploy on the 
node when it boots up. 

Read more in [deployment-implementation/modules](../../docs/deployment-implementation.md#Modules-Provisioning)

### Nested Stacks: nucleus, stateless-body, stateful-body, membrane scaling groups

#### Nucleus
The critical part of the cell is the nucleus, which runs Zookeeper and HDFS namenodes.

The Zookeeper ensemble can be discovered through an ELB over the Zookeeper Exhibitor 
REST API.
Two helper scripts `zk-list-nodes` and `zk-barrier` can be used to respectively: get the 
list of Zookeeper nodes and block for the zk ensemble. 

#### Stateless Body

The stateless body is used for any workload that doesn't have persistent local storage
requirements and, hence, can be scaled down easily, without having to worry about data 
integrity.

#### Stateful Body

The stateful body instead can be scaled up, but in order to scale it down additional
orchestration is required in order to maintain data integrity (e.g. decommission HDFS
datanodes or Kafka brokers)

#### Membrane

The membrane is publicly exposed (all other groups should be private) and hence may have
special security requirements. 
The cell gateway and load balancing services will run in the membrane. 

#### Bastion

The bastion (aka jump host) is used to enable external SSH access into the cell.

## AMI

The default IAM is CentOS-7.2 based, but any compatible AMI should work.

The current AMI has 
[Enhanced Networking](http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/enhanced-networking.html) 
enabled.  
As of cell-os-1.2.0 the AMI has:

```json
"Kernel": 3.10.0-327.4.5.el7.x86_64
"ethtool / driver": ixgbevf  
"ixgbevf": 2.16.1
"SriovNetSupport": "simple"
"DeleteOnTermination": true
"VolumeSize": 200
```

The base provisioning depends on `yum` so it will work on RedHat-compatible OS-es.
This said, it should be fairly simple to adapt to other distributions as most modules are
deployed via Puppet modules that support other distros.

# Troubleshooting

### Can't find SaasBase access key id / secret access key (when using "Launch Stack" button ![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png))
Look for the keys in [http://saasbase.corp.adobe.com/ops/operations/deployment.html](http://saasbase.corp.adobe.com/ops/operations/deployment.html)
The keys are also available in the Secret Server - main dl-saasbase-eng@adobe.com if you
have any issues.

### Stack gets rolled back 

1. Go to [https://console.aws.amazon.com/cloudformation/home](https://console.aws.amazon.com/cloudformation/home).
2. Make sure the correct region is selected.
3. Click on the failed stack.
4. On the bottom half of the screen click "Events".
5. Drill down and see the failure details:

    Parameter validation failed: parameter value for parameter name 
    KeyName does not exist. Rollback requested by user.

In the Cloud Formation form, try selecting an existing KeyName from the dropdown or 
otherwise create a keypair for that region, download it and retry.

### Stack already exists and / or can't delete it
E.g.
```
Error creating cell:  An error occurred (AlreadyExistsException) when calling the 
CreateStack operation: Stack [my-awesome-cell] already exists
```

This means that the CloudFormation stack still already exists.  

If you already delete the cell, it's possible that the stack hasn't been successfully 
deleted by CloudFormation.  
You can try deleting the stack again (it's possible that CF failed for no good reason).

If that doesn't work you should know that this can happen if you created other resources
(e.g. policies, subnets, etc.) that depend on resources in this stack. You'll have to 
manually delete any manually added resource and then retry deleting the stack.

List your stacks

    aws cloudformation describe-stacks
    
See detailed stack events for `$cell_name`

    aws cloudformation describe-stack-events --stack-name $cell_name

To delete the stack 

    aws cloudformation delete-stack --stack-name $cell_name

## Using the CLI to troubleshoot

For cli related issues please check out the [cli doc troubleshooting section](../../docs/cli.md#troubleshooting).  

First check if the stack has succeeded and all VMs are up and finished initializing.
It takes a while.

If your LBs are empty (or some of them are empty) and you're out of patience:

* Tail the logs on a  nucleus node

        ./cell log <cell-name> nucleus

* Alternatively you could ssh into the node

        ./cell ssh <cell-name> nucleus

On nucleus:

Check if Exhibitor is running:

    ./cell cmd <cell-name> nucleus 0 "curl -v localhost:8181/exhibitor/v1/cluster/status"
    ...
    [{"code":3,"description":"serving","hostname":"ip-10-0-0-12","isLeader":true}]

If it doesn't work check if the Zookeeper container is running:

```bash
docker ps
CONTAINER ID        IMAGE                                  COMMAND                CREATED             STATUS              PORTS                                                                                            NAMES
6b17f546e911        mbabineau/zookeeper-exhibitor:latest   "bash -ex /opt/exhib   9 minutes ago       Up 9 minutes        0.0.0.0:2181->2181/tcp, 0.0.0.0:2888->2888/tcp, 0.0.0.0:3888->3888/tcp, 0.0.0.0:8181->8181/tcp   zookeeper
```

You should see it there. Look at the logs:

    docker logs -f zk_zk-1

If it complains about the S3 URL, the bucket may be misconfigured
(e.g. in a different region).


On body

First make sure it's not still blocking for ZK:

    ./cell log cell-1 stateless-body

When blocking it will continuously echo something

IF you want to check the ZK cluster:

    ./cell cmd cell-1 stateless-body 0 /usr/local/bin/zk-list-nodes

This should output at least one entry like:

    ip-10-0-0-173:2181

If it doesn't probably the Exhibitor hasn't finished converging.

Once it gets the ZK cluster it will go ahead and deploy. This may take
a few minutes.

If it's already done check for open ports:

    ./cell cmd cell-1 stateless-body 1 "netstat -tlnp"

Look for 8080 (marathon) and 5050 (mesos master)

    ./cell cmd cell-1 stateless-body 1 "systemctl status mesos-master"
    ./cell cmd cell-1 stateless-body 1 "systemctl status mesos-slave"
    ./cell cmd cell-1 stateless-body 1 "systemctl status marathon"

If they're dead check why

    journalctl -xn -u mesos-mater

They are configured to retry on failure so you can just tail (or look into)
`/var/log/messages` to see what's going on.

I've seen bugs that caused a faulty ZK URI to get into the configurations.

The main place where the config is driven from is `cluster.yaml`

    cat /opt/cell/cluster/cluster.yaml

The mesos configurations are in

    cat /etc/default/mesos-master
    cat /etc/default/mesos-slave

# Notes

## Caveats

### You need a SOCKS proxy to connect to the internal load balancers.

    ./cell proxy cell-1

This opens a SOCKS proxy on localhost:1234 (configurable through `PROXY_PORT` env var)

Then use a browser plugin like foxy proxy

### CAMP accounts can't implicitly create IAM users and roles

The default IT Cloud CAMP AWS accounts are restricted from creating IAM Users and Roles which means
that we need to fallback on passing user's key/secret into the VM. This may work for dev setups but
needs to be discussed with Security and IT.

Note that you may get this capabilities by enabling KLAM and using 1h tokens.

### The bucket needs to be in the same region

Exhibitor doesn't follow S3 redirects and had some issues configuring the region.  
The cli tool will create it for you, but when you launch using the stack you need make sure you're
creating a bucket in the right place as


## TODO

- [x] Switch to official saasbase-installer (1.26 RC2 should be ready soon)
- [x] Add architecture diagram
- [x] Provision everything including the VPC with networks, etc. (see related work)
- [x] Revisit Exhibitor S3 bucket region settings (bucket needs to be in the same region now)
- [ ] [Confd](https://github.com/kelseyhightower/confd) support to automatically handle nucleus 
      size changes. 
- [x] \[CELL-61\] - Add IAM role instead of using keys stored in configuration
- [ ] Optionally use keys instead IAM roles
- [x] Expand body into 2 scaling groups with different timeouts for pre-emption to support stateless
      vs stateful workloads.
- [x] Simplify user data scripts. If we'll not use cached AMIs we can get rid of cleanup steps
- [ ] Create an AWS cluster manifest instead of writing it inline (only need to pass ZK as fact)
- [x] Reconcile with existing implementation if possible (see Related Work below)
- [x] Pick key id, secret from awscli configuration

Speed

- [x] Try removing host/core role to speed things up (added as it complained about `pip2.7`)
- [ ] Configure Exhibitor to converge faster
- [ ] Cache VM AMIs once successfully created and reuse them - need to figure out
      access rights to these AMIs (no CF API for AMIs)
- [ ] Generate AMIs at build time with basic stuff on them (packages and Docker layers?)


## Current node layout
This setup currently places only Zookeeper in the Nucleus and Mesos master and Marathon are part
of the `stateless-body`. 
While this may seem weird, the reason is that neither Mesos master, nor Marathon are
stateful nor do they require special care (they can be stopped and restarted anytime
without a big impact.  
On the other hand Zookeeper is stateful and latency sensitive and also critical to the functioning
of the rest of the cell, so requires isolation.  

We may not want to run either Mesos master or Marathon on every slave, so  we may
end up having a separate scaling group or even scheduling them on top of Mesos and only bootstrap
them at the initial cell provisioning.  

