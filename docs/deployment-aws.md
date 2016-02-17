# cell-os-base on EC2

An initial working prototype for the Amazon EC2-based elastic cell.  

It consists of a CloudFormation template to stand a cell running cell-os-base.  

# cell-os infrastructure diagram
```
+------------------------------------------------------------------------------------+
|   +----------------------------------------------------------------------------+   |
|   |          80                80               80               80            |   |
|   |   +-------------+    +-------------+   +-------------+   +-------------+   |   |
|   |   |    ZK ELB   |    |  Mesos ELB  |   | Marathon ELB|   | Gateway ELB |   |   |
|   |   +------+------+    +------+------+   +------+------+   +------+------+   |   |
|   |          |                  |                 |                 |          |   |
|   |          |         +-----------------------------------------------------+ |   |
|   |          |         |        |                 |                 ^        | |   |
|   |   +------+------+  | +------+------+   +------+------+   +------+------+ | |   |
|   |   | <--|   |--> |  | | <--|   |--> |   | <--|   |--> |   | <--|   |--> | | |   |
|   |   +-------------+  | +-------------+   +-------------+   +-------------+ | |   |
|   |     Nucleus SG     |    Stateless         Stateful          Membrane SG  | |   |
|   |     HDFS NN/QJM    |    Body SG           Body SG                        | |   |
|   |                    |                      HDFS DN                        | |   |
|   |                    +-----------------------------------------------------+ |   |
|   |                               Mesos Agents                                 |   |
|   +----------------------------------------------------------------------------+   |
|     Subnet 1   10.0.0.0/24                                                         |
+------------------------------------------------------------------------------------+
       us-west-2-cell-1 VPC   vpc-62c65107 (10.0.0.0/16)
```

The default cell size is a 1-node nucleus and 1-node stateless body, 0-node stateful body,
1 - node membrane, each in separate scaling groups (i.e. can be scaled up independently).  

The cell-os-base consists of Zookeeper / Exhibitor, Mesos and Marathon.
cel-os 1.1 extended the base with HDFS consisting of QJM, NN running in Nucleus and 
DN running in Stateful Body.  
All other services typically run on top of the base using one of the cell schedulers.  

## Internals: How it's made
With cell-os 1.1 we started using [Troposphere](https://github.com/cloudtools/troposphere)
to generate the AWS CF templates.

## Internals: How it works

There's a main CF stack that sets up the VPC along the rest of the infrastructure pieces
and a 4 nested stacks for individual scaling groups which are created by the main stack.

### Main stack: VPC, Subnets, ELBs, Internet Gateway, Routes, Security Groups, etc.

This sets up the VPC along with the Subnets, Scaling Groups, routes and security around.

This sets up the infrastructure and creates separate scaling groups for each subdivision
of the cell using nested stacks.  

Each cell subdivision is created by passing the role, tags, cell modules and
configurations to the nested stack.

Roles and tags are used to identify the EC2 instances and to set attributes.

### Cell modules provisioning

Each CF nested stack receives a list of cell modules to deploy on the node when it boots up. 

When starting, all the machines download a "seed" .tar.gz file that contains the list of cell modules in the following format: 

    /opt/cell/seed
      00-docker/xx
      00-docker/provision
      10-another-module/provision_post

The list of cell modules is matched against this list of directories, and in each of the directories for a machine, we: 

* check for a `provision` file. This is executed before Zookeeper is available
* check for a `provision_post` file, executed after the Exhibitor / Zookeeper ensemble converges to a final, active state (using the `zk-barrier` script which will block polling for zk).

### Nested Stacks: nucleus, stateless-body, stateful-body, membrane scaling groups

#### Nucleus
The critical part of the cell is the nucleus, which runs Zookeeper and HDFS namenodes.

The Zookeeper ensemble can be discovered through an ELB over the Zookeeper Exhibitor REST API.
Two helper scripts `zk-list-nodes` and `zk-barrier` can be used to respectively: get the list of Zookeeper nodes and block for the zk enesemble. 

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
The cell geteway and load balancing services will run in the membrane. 

# Troubleshooting

## "Launch Stack" button ![](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)

### Can't find SaasBase access key id / secret access key
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

    docker ps
    CONTAINER ID        IMAGE                                  COMMAND                CREATED             STATUS              PORTS                                                                                            NAMES
    6b17f546e911        mbabineau/zookeeper-exhibitor:latest   "bash -ex /opt/exhib   9 minutes ago       Up 9 minutes        0.0.0.0:2181->2181/tcp, 0.0.0.0:2888->2888/tcp, 0.0.0.0:3888->3888/tcp, 0.0.0.0:8181->8181/tcp   zk_zk-1

You should see it there. Look at the logs:

    docker logs -f zk_zk-1

If it complains about the S3 URL, the bucket may be in a separate region. 


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

### You need a SOCKS proxy to connect to the load balancers.

    ./cell proxy cell-1 nucleus

This opens a SOCKS proxy on localhost:1234 (configurable throuh `PROXY_PORT` env var)

Then use a browser plugin like foxy proxy

### CAMP accounts can't implicitly create IAM users and roles

The default IT Cloud CAMP AWS accounts are restricted from creating IAM Users and Roles which means
that we need to fallback on passing user's key/secret into the VM. This may work for dev setups but
needs to be discussed with Security and IT.

Note that you may get this capabilities by enabling KLAM  

### The bucket needs to be in the same region

Exhibitor doesn't follow S3 redirects and had some issues configuring the region.  
The cli tool will create it for you, but when you launch using the stack you need make sure you're
creating a bucket in the right place as


## TODO

- [x] Switch to official saasbase-installer (1.26 RC2 should be ready soon)
- [x] Add architecture diagram
- [x] Provision everything including the VPC with networks, etc. (see related work)
- [ ] Revisit Exhibitor S3 bucket region settings (bucket needs to be in the same region now)
- [ ] [Confd](https://github.com/kelseyhightower/confd) support to automatically handle nucleus 
      size changes. 
- [x] \[CELL-61\] - Add IAM role instead of using keys stored in configuration
- [ ] Optionally use keys instead IAM roles
- [x] Expand body into 2 scaling groups with different timeouts for pre-emption to support stateless
      vs stateful workloads.
- [x] Simplify user data scripts. If we'll not use cached AMIs we can get rid of cleanup steps
- [ ] Create an AWS cluster manifest instead of writing it inline (only need to pass ZK as fact)
- [ ] Reconcile with existing implementation if possible (see Related Work below)
- [ ] Pick key id, secret from awscli configuration

Speed

- [x] Try removing host/core role to speed things up (added as it complained about `pip2.7`)
- [ ] Configure Exhibitor to converge faster
- [ ] Cache VM AMIs once successfully created and reuse them - need to figure out
      access rights to these AMIs (no CF API for AMIs)
- [ ] Generate AMIs at build time with basic stuff on them (packages and Docker layers?)

## Raw CF JSON vs Troposphere vs Terraform
I wrote this directly in CF as it was simpler to get started (i.e. copy pasting from examples) but
then I realized JSON is not that bad.  

Troposphere is a nice Python wrapper that can generate a CF template.  
Having python is nice, but I'm not sure it's necessarily simpler or with less code:  

* This template has less than 500 lines
* Raw JSON is declarative and Python is imperative (can make it much more unreadable than the JSON)
* JSON supports hierarchies easily, while in Python object names need to be repeated for every
property

Terraform is declarative and also (presumably) works across several other cloud providers.  
It comes with it's own DSL which does resemble familiar things but likely can't be managed
programmatically.  

## Related work

Behance has some nice work similar to this using Troposphere and CoreOS instead of CentOS.
Github repo here https://github.com/behance/mesos-cluster (note that it requires explicit
access - talk to fortier@adobe.com).  
It would be worthwhile evaluating if we shouldn't try to have a common base which we can reuse.  
The overall infrastructure (VPCs, scaling groups, load balancers, security groups, etc.) should
look the same and could have some specifics layered on top.  


## Current node layout
This setup currently places only Zookeeper in the Nucleus and Mesos master and Marathon are part
of the body. 
While this may seem weird, the reason is that neither Mesos master, nor Marathon are
stateful nor do they require special care (they can be stopped and restarted anytime
without a big impact.  
On the other hand Zookeeper is stateful and latency sensitive and also critical to the functioning
of the rest of the cell, so requires special attention.  

We may not want to run either Mesos master or Marathon on every slave, however so perhaps we may
end up having a separate scaling group or even scheduling them on top of Mesos and only bootstrap
them at the initial cell provisioning.  
