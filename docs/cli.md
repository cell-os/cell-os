<!-- TOC depthFrom:1 depthTo:6 withLinks:1 updateOnSave:1 orderedList:0 -->

 - [Installation](#installation)
  - [Docker](#docker)
  - [Classic](#classic)
 - [Environment](#environment)
 - [Usage](#usage)
 - [dcos-cli integration](#dcos-cli-integration)
 - [Advanced: Accessing the cell's internal services over HTTP](#advanced-accessing-the-cells-internal-services-over-http)
 - [Advanced](#advanced)
 - [`.generated` directory](#generated-directory)

<!-- /TOC -->

## Installation

### Docker
**BETA**

```
    docker run -it \
      -e "AWS_DEFAULT_REGION=us-west-1" \
      -e "AWS_ACCESS_KEY_ID=XXXXXXXXXXXXXXXX" \
      -e "AWS_SECRET_ACCESS_KEY=YYYYYYYYYYYYYYYYYYYYYYYY" \
      -v /tmp/generated/:/cellos/.generated \
      -v /tmp/aws:/root/.aws \
      -v /tmp/cellos:/root/.cellos \
      -v /tmp/dcos:/root/.dcos \
      docker-cell-os.dr.corp.adobe.com/cellos
```

> **Pro tip:** you can set an alias like `alias cell='docker run -it -e ...'`

> **Note**:
On OSX / Windows if your host sleeps, time may get out of sync and cause AWS API
 problems. Restarting Docker will fix this.
 [Details](https://forums.docker.com/t/syncing-clock-with-host/10432)

### Classic

 #### **Step 0**: Activate virtualenv

     virtualenv env
     source env/bin/activate

 #### **Step 0**: Configure [AWS CLI](http://aws.amazon.com/cli/)
 The cell CLI tool is using a bunch of Python packages, that talk to AWS:

     aws configure

 > NOTE  
 You will need an [acccess key id and secret access key](http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html) for this.
 Contact your account manager if you don't have one.

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

## Environment

The AWS region is picked from the AWS CLI configuration / environment
(`AWS_DEFAULT_REGION`)

## Usage

    ./cell --help

```
Usage:
  cell create <cell-name>
  cell update <cell-name>
  cell delete <cell-name>
  cell list [<cell-name>]
  ...

For additional help use dl-metal-cell-users@adobe.com.
For development related questions use dl-metal-cell-dev@adobe.com
Github git.corp.adobe.com/metal-cell/cell-os
Slack https://adobe.slack.com/messages/metal-cell/
```

**Create a new cell**

    ./cell create cell-1

It normally takes up to 12-15 minutes to complete during which there are 3 main stages
* infrastructure provisioning
* cell-os-base provision pre
* cell-os-base provision post

The last two stages are separated by a "barrier" that ensures Zookeeper is ready before 
deploying the rest of the cell-os base.

**List all -cells- stacks**

    ./cell list

```  
--------------------------------------------------------------------------------------------
|                                           list                                           |
+----+------------+------------------+---------------+-------------------------------------+
|  c1|  us-west-1 |  CREATE_COMPLETE |  1.2-SNAPSHOT |  2016-03-01 22:17:15.013000+00:00   |
|  c3|  us-west-1 |  CREATE_COMPLETE |  1.2-SNAPSHOT |  2016-02-25 21:05:31.530000+00:00   |
+----+------------+------------------+---------------+-------------------------------------+
```

**Watch the progress of your cell's infrastructure provisioning**

    ./cell log cell-1

```
+---------------------------+--------------------------------+---------------------+
|  2015-08-13T20:34:44.565Z |  us-east-1-cell-1              |  CREATE_COMPLETE    |
|  2015-08-13T20:34:41.465Z |  Nucleus                       |  CREATE_COMPLETE    |
|  2015-08-13T20:33:22.194Z |  Nucleus                       |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:21.280Z |  Nucleus                       |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:19.120Z |  NucleusLaunchConfig           |  CREATE_COMPLETE    |
|  2015-08-13T20:33:18.755Z |  NucleusLaunchConfig           |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:17.977Z |  NucleusLaunchConfig           |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:16.154Z |  NucleusInstanceProfile        |  CREATE_COMPLETE    |
|  2015-08-13T20:33:01.718Z |  StatelessBody                 |  CREATE_COMPLETE    |
+---------------------------+--------------------------------+---------------------+
```

Once the provisioning of the infrastructure is done the first stage (pre) begins.
You can watch the progress across all nodes with detailed timings in the cell provisioning status page:
`http://cell-os--<CELL>.s3-us-west-1.amazonaws.com/cell-os--<CELL>/shared/status/status.html`

> **NOTE**: the actual status page link is displayed after cell creation and in the cell `list` results.


**Tail the provisioning logs of individual nodes:**

    ./cell log cell-1 nucleus 1

```
Aug 13 20:36:10 ip-172-31-15-216 cloud-init: CloudFormation signaled successfully with SUCCESS.
Aug 13 20:36:10 ip-172-31-15-216 cloud-init: Cloud-init v. 0.7.5 finished at Thu, 13 Aug 2015 20:36:10 +0000. Datasource DataSourceEc2.  Up 89.60 seconds
```

**Listing your cell**

    ./cell list cell-1

```
-------------------------------------------------------------
|                          nucleus                          |
+-----------------+-------------+----------------+----------+
|  127.127.41.163  |  10.0.0.140 |  ami-59addb39  |  running |
|  127.127.157.213 |  10.0.0.141 |  ami-59addb39  |  running |
|  127.127.174.120 |  10.0.0.139 |  ami-59addb39  |  running |
+-----------------+-------------+----------------+----------+

----------------------------------------------------------
|                     stateless-body                     |
+----------------+-----------+----------------+----------+
|  127.127.41.127 |  10.0.0.9 |  ami-59addb39  |  running |
+----------------+-----------+----------------+----------+

----------------------------------------------------------
|                      stateful-body                     |
+---------------+------------+----------------+----------+
|  127.127.36.53 |  10.0.0.35 |  ami-59addb39  |  running |
+---------------+------------+----------------+----------+

-----------------------------------------------------------
|                        membrane                         |
+---------------+-------------+----------------+----------+
|  127.127.41.42 |  10.0.0.213 |  ami-59addb39  |  running |
+---------------+-------------+----------------+----------+

--------------------------------------------------------------------------------------------------------
|                                              Status Page                                             |
+-------------+----------------------------------------------------------------------------------------+
|  status_page|  http://cell-os--c1.s3-us-west-1.amazonaws.com/cell-os--c1/shared/status/status.html   |
+-------------+----------------------------------------------------------------------------------------+

----------------------------------------------------------------------------------
|                                      ELBs                                      |
+--------------+-----------------------------------------------------------------+
|  c1-membrane |  c1-membrane-401796130.us-west-1.elb.amazonaws.com              |
|  c1-mesos    |  internal-c1-mesos-1528395697.us-west-1.elb.amazonaws.com       |
|  c1-zookeeper|  internal-c1-zookeeper-1743906954.us-west-1.elb.amazonaws.com   |
|  c1-marathon |  internal-c1-marathon-1356260519.us-west-1.elb.amazonaws.com    |
+--------------+-----------------------------------------------------------------+

-------------------------------------------------------------
|                          Gateway                          |
+-----------+-----------------------------------------------+
|  zookeeper|  http://zookeeper.gw.c1.metal-cell.adobe.io   |
|  mesos    |  http://mesos.gw.c1.metal-cell.adobe.io       |
|  marathon |  http://marathon.gw.c1.metal-cell.adobe.io    |
|  hdfs     |  http://hdfs.gw.c1.metal-cell.adobe.io        |
+-----------+-----------------------------------------------+
```

The cell listing shows each node in each cell subdivision (nucleus, bodies and membrane)

The `Status` listing has a link to the cell-os-base provisioning status page.
This is only useful during initial provisioning.

`ELBs` section lists all (ELB) load balancers. 
Only the membrane ELB is available externally. For all others you'll need to first `proxy` into
the cell and access them through an SSH tunnel, or through VPN (not provisioned with the cell, yet).

The last part, `Gateway` is the most important. This shows the cell endpoints for the base
services.


> **NOTE**  
Access to these endpoints is restricted to certain whitelisted networks.  
You can share links of the gateway endpoints.


**SSH into your first nucleus VM**

    ./cell ssh <cell-name> nucleus 1

**SSH into all the instances in your cell using `mux`**

Install the `tmux`/`tmuxinator` combo on your machine:

    brew install tmux
    sudo gem install tmuxinator

Once all that is in place, you can SSH into all your cell instances:

    ./cell mux <cell-name>

This will launch a `tmux` session with a separate window for each role. In each window,
multiple SSH sessions are started in tiled mode (one for each instance in the corresponding role).


**SSH into all the instances in your cell using `i2cssh` and iTerm2**

    brew cask install iterm2
    sudo gem install i2cssh

    ./cell i2cssh <cell-name> [role]

**Run commands on the cell nodes**

    ./cell cmd us-east-1-cell-1 nucleus 1 "sudo -u root docker logs -f zk_zk-1"

> **NOTE:** Only one node can be targeted at a time. 

> **NOTE**  
While we don't recommend this approach, if you feel like you need to manually manage your cell, 
consider using something like Ansible or Salt.

**Scale up / down the cell**

Both the nucleus, the bodies and the membrane can be scaled

    ./cell scale cell-1 stateless-body 5
    Scaling group cell-1-StatelessBody-1OSD7WF08DJYE

    ./cell list cell-1
    load balancers
    |  cell-1-lb-mesos   |  internal-cell-1-lb-mesos-620460102.us-west-2.elb.amazonaws.com       |
    |  cell-1-lb-marathon|  internal-cell-1-lb-marathon-1214246100.us-west-2.elb.amazonaws.com   |
    |  cell-1-lb-zk      |  internal-cell-1-lb-zk-18429062.us-west-2.elb.amazonaws.com           |
    nucleus
    127.127.185.97  10.0.0.173  ami-c7d092f7  running us-west-2-cell-1
    stateless-body
    127.127.201.215 10.0.0.175  ami-c7d092f7  running us-west-2-cell-1
    127.127.197.106 10.0.0.172  ami-c7d092f7  running us-west-2-cell-1
    127.127.206.98  10.0.0.174  ami-c7d092f7  running us-west-2-cell-1
    127.127.196.197 10.0.0.176  ami-c7d092f7  running us-west-2-cell-1
    127.127.68.19   10.0.0.40   ami-c7d092f7  running us-west-2-cell-1

    ./cell scale cell-1 stateless-body 1

> **NOTE:**  
Scaling the Nucleus down may cause Zookeeper and HDFS unavailability and, as a result, 
a wider failure for dependent services.

## dcos-cli integration

The CellOS CLI integrates with the [dcos-cli](https://github.com/mesosphere/dcos-cli). 
For convenience we wrap the dcos-cli and automatically configure it to work across all your cells.

instead of `dcos command` you need to run `./cell dcos <cell-name> command`

```
./cell dcos c1 help
Running dcos help...
Command line utility for the Mesosphere Datacenter Operating
System (DCOS). The Mesosphere DCOS is a distributed operating
system built around Apache Mesos. This utility provides tools
for easy management of a DCOS installation.

Available DCOS commands:

	config         	Get and set DCOS CLI configuration properties
	help           	Display command line usage information
	marathon       	Deploy and manage applications on the DCOS
	node           	Manage DCOS nodes
	package        	Install and manage DCOS packages
	service        	Manage DCOS services
	task           	Manage DCOS tasks

Get detailed command description with 'dcos <command> --help'.
```

> **NOTE**  
You can still use the dcos-cli directly.  
The actual configuration resides in `<cellos-home>/.generated/<cell-name>`
```
cat .generated/c1/dcos.toml
[core]
mesos_master_url = "http://mesos.gw.c1.metal-cell.adobe.io"
reporting = false
email = "cell@metal-cell.adobe.io"
cell_url = "http://{service}.gw.c1.metal-cell.adobe.io"
[marathon]
url = "http://marathon.gw.c1.metal-cell.adobe.io"
[package]
sources = [ "https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-1.2-SNAPSHOT.zip"]
cache = "/Users/clehene/metal-cell/cell-os/.generated/c1//dcos_tmp"
```
The universe repositories caches are in `<cell-home>/.generated/<cell-name>/dcos_tmp`

For more information on how to use the dcos-cli use the help or see the 
[dcos-cli official documentation](https://docs.mesosphere.com/administration/introcli/cli/).

## Advanced: Accessing the cell's internal services over HTTP

By default, cell services and load balancers are internal and cannot be accessed
directly over the Internet. 

To reach the cell services you need to open a tunnel / proxy 

    ssh -D 1234 centos@127.127.68.19 -i ~/.ssh/servers/us-west-2-cell-1.pem

    or

    ./cell proxy cell-1 nucleus

The above two commands are equivalent, and open a SOCKS4/5 proxy on localhost, port 1234.
This proxy can then be used by SOCKS-compatible clients to communicate with hosts in the cell.
It is common to install a browser plugin like FoxyProxy to help facilitate the easy usage 
of SOCKS proxies. With the proxy configured, you can browse to hostnames and ports that
would otherwise be only available inside of the cell.

For example, you can use curl with `--proxy socks5h://localhost:1234` to access exposed HTTP services using this proxy:

    curl -s --proxy socks5h://localhost:1234 internal-cell-1-lb-marathon-1214246100.us-west-2.elb.amazonaws.com/v2/info | python -m json.tool
    {
        "elected": true,
        "leader": "ip-10-0-0-40:8080",
        ...
    }

## Advanced

# `.generated` directory
The `.generated` contains local cell configurations and caches.

The structure is
```
.generated/
  <cell-1>
  <cell-2>
  ...
```

For each cell we store

`config.yaml` - cell level configuration containing cell name, zk, mesos and
marathon endpoints

CF template files generated by troposphere:
* elastic-cell.json
* elastic-cell-scaling-group.json

`cell-os--<cell-name>.pem` - generated SSH key pair
`ssh_config` - SSH configuration (passed with `-F` to ssh commands)

* dcos:
  * `dcos.toml` - standard DCOS configuration
    * `mesos_master_url`
    * `cell_url`
    * `marathon_url`
    * package sources list
  * `dcos_tmp` - package repo cache
  * dcos package config templates and generated configs (e.g.
  `<package>.json.template`, `<package>.json`

`seed.tar.gz` - `deploy/seed` archive

