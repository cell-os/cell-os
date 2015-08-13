# CLI
The CLI is a convenience wrapper around the [AWS CLI](http://aws.amazon.com/cli/)

    pip install awscli
    aws configure

## Environment

The AWS region is picked from the AWS CLI configuration / environment.  
Run `./cell help` to see how to customize your EC2 keypair, and all other options.  

## Usage

$ ./cell help

```
  cell-os cli utility 1.1-SNAPSHOT

  usage: ./cell <action> <cell-name> [nucleus|body] [<index>] [<command>]
   actions:
     create <cell-name> - creates a new cell
     delete <cell-name> - deletes an existing cell
     list <cell-name> - lists existing stacks or the nodes in a cell
     scale <cell-name> <role> <capacity> - scales role to desired capacity
     ssh <cell-name> <role> [<index>] - ssh to first node in role or to index
     log <cell-name> [<role>] [<index>] - tail stack events or nodes deploy log
     cmd <cell-name> <role> <index> - run command on node n
     proxy <cell-name> <role> - open SOCKS proxy to first node in <role>

  Environment variables:

    AWS_KEY_PAIR - EC2 ssh keypir to use (defaults to first on the account)
    KEYPATH - the local path where <keypair>.pem is found (defaults to
      /Users/clehene/.ssh). The .pem extension is required.
    PROXY_PORT - the SOCKS5 proxy port (defaults to 1234)

  All AWS CLI environment variables (e.g. AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY, etc.) and configs apply.

  This CLI is a convenience tool, not intended as an exhaustive cluster manager.
  For advanced use-cases please use the AWS CLI or the AWS web console.

  For additional help use dl-metal-cell-users@adobe.com.
  For development related questions use dl-metal-cell-dev@adobe.com
  Github git.corp.adobe.com/metal-cell/cell-os
  Slack https://adobe.slack.com/messages/metal-cell/
```

**Prerequisites**

    export AWS_KEY_PAIR=<the EC2 keypair that should be used. Defaults to first key on thee acount>
    export KEYPATH=<the location of your ${AWS_KEY_PAIR}.pem (must end in .pem).defaults to ~/.ssh>

**Create a new cell**

    ./cell create cell-1

This will return the CloudFormation Stack ARN or an error.  
You can [watch the stack form](https://console.aws.amazon.com/cloudformation/home)

It can take up to a few minutes once the stack is complete as it takes a while for
Exhibitor to do the discovery through S3 and the body nodes will wait until they have
a working Zookeeper before deploying the cell-os-base software

Once it's done the [load balancers](https://us-west-2.console.aws.amazon.com/ec2/v2/home?region=us-west-2#LoadBalancers:)
should be reaching the instances


**List all -cells- stacks**

    ./cell list
    -----------------------------------------------
    |                 ListStacks                  |
    +-----------------+-------------------+-------+
    |  cell-1         |  CREATE_COMPLETE  |  None |
    +-----------------+-------------------+-------+

**Watch the progress of your cell's creation**

    ./cell log cell-1

```
+---------------------------+-----------------------------------------------------------+---------------------+
|  2015-08-13T20:34:44.565Z |  us-east-1-cell-1                                         |  CREATE_COMPLETE    |
|  2015-08-13T20:34:41.465Z |  Nucleus                                                  |  CREATE_COMPLETE    |
|  2015-08-13T20:33:22.194Z |  Nucleus                                                  |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:21.280Z |  Nucleus                                                  |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:19.120Z |  NucleusLaunchConfig                                      |  CREATE_COMPLETE    |
|  2015-08-13T20:33:18.755Z |  NucleusLaunchConfig                                      |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:17.977Z |  NucleusLaunchConfig                                      |  CREATE_IN_PROGRESS |
|  2015-08-13T20:33:16.154Z |  NucleusInstanceProfile                                   |  CREATE_COMPLETE    |
|  2015-08-13T20:33:01.718Z |  StatelessBody                                            |  CREATE_COMPLETE    |
|  2015-08-13T20:32:21.592Z |  NucleusToNucleusSecurityGroupIngressToAvoidCircularDeps  |  CREATE_COMPLETE    |
+---------------------------+-----------------------------------------------------------+---------------------+
```

**Tail the provisioning logs of your cell's nucleus / body**

    ./cell log cell-1 nucleus 1

```
Aug 13 20:36:10 ip-172-31-15-216 cloud-init: CloudFormation signaled successfully with SUCCESS.
Aug 13 20:36:10 ip-172-31-15-216 cloud-init: Cloud-init v. 0.7.5 finished at Thu, 13 Aug 2015 20:36:10 +0000. Datasource DataSourceEc2.  Up 89.60 seconds
```

**List VMs in your cell**

    # note that that's not the cell id so doesn't have the region
    $ ./cell list cell-1
    nucleus
    127.127.189.82  i-5aa897ac  ami-c7d092f7  us-west-2-cell-1
    body
    127.127.84.3  i-97a89761  ami-c7d092f7  us-west-2-cell-1

**SSH into your first nucleus VM**

    ./cell ssh <cell-name> nucleus
    # IMMV check your keys..

**Run commands on the cell nodes**

    ./cell cmd us-east-1-cell-1 nucleus 1 "sudo -u root docker logs -f zk_zk-1"

**Scale up / down the cell**

Both the nucleus and the body can be scaled

    ./cell scale cell-1 body 5
    Scaling group cell-1-StatelessBody-1OSD7WF08DJYE

    ./cell list cell-1
    load balancers
    |  cell-1-lb-mesos   |  internal-cell-1-lb-mesos-620460102.us-west-2.elb.amazonaws.com       |
    |  cell-1-lb-marathon|  internal-cell-1-lb-marathon-1214246100.us-west-2.elb.amazonaws.com   |
    |  cell-1-lb-zk      |  internal-cell-1-lb-zk-18429062.us-west-2.elb.amazonaws.com           |
    nucleus
    127.127.185.97  10.0.0.173  ami-c7d092f7  running us-west-2-cell-1
    body
    127.127.201.215 10.0.0.175  ami-c7d092f7  running us-west-2-cell-1
    127.127.197.106 10.0.0.172  ami-c7d092f7  running us-west-2-cell-1
    127.127.206.98  10.0.0.174  ami-c7d092f7  running us-west-2-cell-1
    127.127.196.197 10.0.0.176  ami-c7d092f7  running us-west-2-cell-1
    127.127.68.19   10.0.0.40   ami-c7d092f7  running us-west-2-cell-1

    ./cell scale cell-1 body 1


## Accessing the cell's internal services over HTTP

By default cell services and load balancers are internal, hence can't be accessed
directly over internet. 

To reach the cell services you need to open a tunnel / proxy 

    ssh -D 1234 centos@127.127.68.19 -i ~/.ssh/servers/us-west-2-cell-1.pem

    or

    ./cell proxy cell-1 nucleus


Opens a SOCKS proxy on port 1234 locally. You can then use curl with `--proxy socks5h://localhost:1234` to access the services e.g.

    curl -s --proxy socks5h://localhost:1234 internal-cell-1-lb-marathon-1214246100.us-west-2.elb.amazonaws.com/v2/info | python -m json.tool
    {
        "elected": true,
        "leader": "ip-10-0-0-40:8080",
        ...
    }


