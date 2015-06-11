# CLI
The CLI is a convenience wrapper around the [AWS CLI](http://aws.amazon.com/cli/)

    pip install awscli
    aws configure

## Environment

Set your AWS keys

    export AWS_ACCESS_KEY_ID=<your access key id>
    export AWS_SECRET_ACCESS_KEY=<your secret access key>

## Usage

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


