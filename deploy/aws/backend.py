import os
import re
import sh
import sys
import traceback

import yaml

if os.name == 'posix' and sys.version_info[0] < 3:
    pass
else:
    pass

import boto3
import boto3.session
import jmespath


def first(*args):
    for item in args:
        if item is not None:
            return item
    return None


class KeyException(Exception):
    pass


class AwsBackend(object):
    name = "aws"

    def __init__(self, config, base):
        self.config = config
        self.base = base
        self.session = boto3.session.Session(
            region_name=self.region,
            aws_access_key_id=self.config.aws_access_key_id,
            aws_secret_access_key=self.config.aws_secret_access_key
        )
        self.cfn = self.session.resource('cloudformation')
        self.s3 = self.session.resource('s3')
        self.ec2 = self.session.client('ec2')
        self.elb = self.session.client('elb')
        self.asg = self.session.client('autoscaling')

        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(pkg_dir, '../config/cell.yaml'), 'r') as stream:
            cell = yaml.load(stream)
            ip_allocation = cell['nat_egress_ip']
            self.eip_allocation = ip_allocation if ip_allocation else ''

    @property
    def region(self):
        return first(
            os.getenv('AWS_DEFAULT_REGION'),
            self.config.region,
            'us-west-1'
        )

    @property
    def existing_bucket(self):
        return first(
            os.getenv('CELL_BUCKET'),
            self.config.aws_bucket
        )

    @property
    def bucket(self):
        return first(
            os.getenv('CELL_BUCKET'),
            self.config.aws_bucket,
            self.base.full_cell
        )

    @property
    def dns_name(self):
        return "gw.{cell}.metal-cell.adobe.io".format(cell=self.base.cell)

    @property
    def statuspage(self):
        # s3 endpoint is not consistent across AWS regions
        # in us-east-1 the endpoint doesn't contain the region in the url
        s3_endpoint = "s3-{region}.amazonaws.com".format(region=self.region).replace('us-east-1', 'external-1')
        return "http://{full_cell}.{s3_endpoint}/{full_cell}/shared/status/status.html".format(
            full_cell=self.base.full_cell,
            s3_endpoint=s3_endpoint
        )

    def gateway(self, service):
        return "http://{}.{}".format(service, self.dns_name)

    @property
    def stack(self):
        return self.base.cell

    def cell_exists(self):
        try:
            # if the cell parameter is defined, check it
            if self.base.cell is not None:
                tmp = self.session.client('cloudformation').describe_stacks(
                    StackName=self.base.cell
                )
                return tmp is not None
        except Exception:
            return False

    def build_stack_files(self):
        dir = self.base.cell_dir
        sh.mkdir("-p", dir + "/deploy/aws/build/config")

        args = [dir + "/deploy/aws/elastic-cell.py"]
        if self.base.template_url:
            args += ["--template-url", self.base.template_url]
        if self.base.cidr:
            args += ["--cidr", self.base.cidr]
        args += ["--net-whitelist", self.base.tmp_dir + "/net-whitelist.json"]
        print "Building stack ..."
        sh.python(args, _out=self.base.tmp_dir + "/elastic-cell.json")
        print "Building sub-stack ..."
        sh.python([dir + "/deploy/aws/elastic-cell-scaling-group.py"],
                  _out=self.base.tmp_dir + "/elastic-cell-scaling-group.json")

    def build(self):
        self.build_stack_files()

    def create_bucket(self):
        if not self.existing_bucket:
            print "CREATE bucket s3://{} in {}".format(self.bucket, self.region)
            # See https://github.com/boto/boto3/issues/125
            if self.region != 'us-east-1':
                self.s3.create_bucket(
                    Bucket=self.bucket,
                    CreateBucketConfiguration={
                        'LocationConstraint': self.region
                    }
                )
            else:
                self.s3.create_bucket(Bucket=self.bucket)

        else:
            print "Using existing bucket s3://{}".format(self.existing_bucket)

        bucket = self.s3.Bucket(self.bucket)
        cors = bucket.Cors()
        config = {
            "CORSRules": [{
                "AllowedMethods": ["GET"],
                "AllowedOrigins": ["*"],
            }]
        }
        cors.put(CORSConfiguration=config)

    def seed(self):

        self.upload(self.base.tmp_dir + "/seed.tar.gz", "/shared/cell-os/")
        dir = self.base.cell_dir
        self.upload(
            "{}/cell-os-base.yaml".format(dir),
            "/shared/cell-os/cell-os-base-{}.yaml".format(self.base.version)
        )
        self.upload(dir + "/deploy/aws/resources/status.html",
                    "/shared/status/",
                    extra_args={"ContentType": "text/html"})
        self.upload(dir + "/deploy/machine/user-data",
                    "/shared/cell-os/")

    def delete_bucket(self):
        if not self.existing_bucket:
            delete_response = self.s3.Bucket(self.bucket).objects.delete()
            print "DELETE s3://{}".format(self.bucket)
            self.s3.Bucket(self.bucket).delete()
        else:
            print "DELETE s3://{}/{}".format(self.bucket, self.base.full_cell)  # only delete bucket sub-folder
            delete_response = self.s3.Bucket(self.bucket).objects.filter(Prefix=self.base.full_cell).delete()
        if len(delete_response) > 0:
            for f in delete_response[0]['Deleted']:
                print "DELETE s3://{}".format(f['Key'])

    def create_key(self):
        # check key
        check_result = self.ec2.describe_key_pairs()
        key_exists = len([k['KeyName'] for k in check_result['KeyPairs'] if k['KeyName'] == self.base.full_cell]) > 0
        if key_exists:
            print """\
            Keypair conflict.
            Trying to create {} in {}, but it already exists.
            Please:
                - delete it (aws ec2 delete-key-pair --key-name {})
                - try another cell name
            """.format(self.base.full_cell, self.base.key_file, self.base.full_cell)
            raise KeyException()
        print "CREATE key pair {} -> {}".format(self.base.full_cell, self.base.key_file)
        result = self.ec2.create_key_pair(
            KeyName=self.base.full_cell
        )
        with open(self.base.key_file, "wb+") as f:
            f.write(result['KeyMaterial'])
            f.flush()
        os.chmod(self.base.key_file, 0600)

    def delete_key(self):
        print "DELETE keypair {}".format(self.base.full_cell)
        self.ec2.delete_key_pair(KeyName=self.base.full_cell)

    def upload(self, path, key, extra_args={}):
        """
        Uploads a file to S3
            - either to a subdirectory - appends the file name
              afile -> /subdir/afile
            - or directly to another file (a -> /subdir/b)
              afile -> /subdir/bfile
        Arguments:
            path - full local file path
            key - key to upload to s3,
            extra_args - extra args passed through to the boto3 s3.upload_file method
        """
        if key.endswith("/"):
            key += os.path.basename(path)
        if key.startswith("/"):
            key = key[1:]
        remote_path = self.base.full_cell + "/" + key
        self.s3.meta.client.upload_file(path, self.bucket, remote_path, ExtraArgs=extra_args)
        print "UPLOADED {} to s3://{}/{}".format(path, self.bucket, remote_path)

    def bastion(self):
        role = 'bastion' if self.version() > "1.2.0" else 'stateless-body'
        result = self.instances(role=role, format="PublicIpAddress,Tags")
        if result:
            return result[0][0]

    def proxy(self):
        """
            The node that should be used a SOCKS proxy.
            Bastion should be limited to SSH (port 22) access only so proxying
            should through bastion and then to a node that has enough access to
            act as a proxy.
        :return: the IP of the proxy
        """
        result = self.instances(role='stateless-body', format="PrivateIpAddress")
        return result[0][0] if result else None

    def instances(self, role=None, format="PublicIpAddress, PrivateIpAddress, InstanceId, ImageId, State.Name"):
        filters = [
            {
                'Name': 'tag:cell',
                'Values': [self.base.cell],
            },
            {
                'Name': 'instance-state-name',
                'Values': ['*ing'],
            },
        ]
        if role:
            filters.append(
                {
                    'Name': 'tag:role',
                    'Values': [role],
                }
            )
        tmp = jmespath.search(
            "Reservations[*].Instances[*][].[{}]".format(format),
            self.ec2.describe_instances(
                Filters=filters
            )
        )
        return tmp

    def stack_action(self, action="create"):
        self.build_stack_files()
        self.upload(self.base.tmp_dir + "/elastic-cell.json", "/")
        self.upload(self.base.tmp_dir + "/elastic-cell-scaling-group.json", "/")
        parameters = [
                {
                    'ParameterKey': 'CellName',
                    'ParameterValue': self.base.cell,
                },
                {
                    'ParameterKey': 'CellOsVersionBundle',
                    'ParameterValue': "cell-os-base-{}".format(self.base.version),
                },
                {
                    'ParameterKey': 'KeyName',
                    'ParameterValue': self.base.full_cell,
                },
                {
                    'ParameterKey': 'BucketName',
                    'ParameterValue': self.bucket,
                },
                {
                    'ParameterKey': 'SaasBaseAccessKeyId',
                    'ParameterValue': self.base.saasbase_access_key_id,
                },
                {
                    'ParameterKey': 'SaasBaseSecretAccessKey',
                    'ParameterValue': self.base.saasbase_secret_access_key,
                },
                {
                    'ParameterKey': 'Repository',
                    'ParameterValue': self.base.repository,
                },

            ]
        if len(self.eip_allocation) > 0:
            parameters.append({
                    'ParameterKey': 'EipAllocation',
                    'ParameterValue': self.eip_allocation,
                })
        template_url = "https://s3.amazonaws.com/{}/{}/elastic-cell.json".format(self.bucket, self.base.full_cell)
        print "{} {}".format(action.upper(), self.stack)
        if action == "create":
            stack = self.cfn.create_stack(
                StackName=self.stack,
                Parameters=parameters,
                TemplateURL=template_url,
                DisableRollback=True,
                Capabilities=[
                    'CAPABILITY_IAM',
                ],
                Tags=[
                    {
                        'Key': 'name',
                        'Value': self.base.cell
                    },
                    {
                        'Key': 'version',
                        'Value': self.base.version
                    },
                ]
            )
        elif action == "update":
            response = self.cfn.meta.client.update_stack(
                StackName=self.stack,
                Parameters=parameters,
                TemplateURL=template_url,
                Capabilities=[
                    'CAPABILITY_IAM',
                ],
            )
            print response

    def create(self):
        try:
            self.create_bucket()
        except Exception:
            traceback.print_exc(file=sys.stdout)
            raise
        try:
            self.create_key()
        except Exception:
            self.delete_bucket()
            traceback.print_exc(file=sys.stdout)
            raise
        try:
            self.seed()
            self.stack_action()
        except Exception as e:
            print "Error creating cell: ", e
            try:
                self.delete_key()
            except Exception as e:
                print "Error deleting key", e
            self.delete_bucket()
            traceback.print_exc(file=sys.stdout)
            raise

    def create_message(self):
        return """
        For detailed debugging logs, go to CloudWatch:
            https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logs:
        For detailed status (times included), navigate to
            {statuspage}

        """.format(region=self.region, statuspage=self.statuspage)

    def update(self):
        self.seed()
        self.stack_action(action='update')

    def delete(self):
        print "Deleting stack {}".format(self.stack)
        self.cfn.meta.client.delete_stack(
            StackName=self.stack
        )
        self.delete_key()
        self.delete_bucket()

    def get_role_capacity(self, role):
        (group, current_capacity) = jmespath.search(
            "AutoScalingGroups[? (Tags[? Key=='role' && Value=='{}'] && Tags[?Key=='cell' && Value=='{}'])].[AutoScalingGroupName, DesiredCapacity]".format(
                role,
                self.base.cell
            ),
            self.asg.describe_auto_scaling_groups()
        )[0]
        return group, current_capacity

    def scale(self, role, group_id, capacity):
        self.asg.update_auto_scaling_group(
            AutoScalingGroupName=group_id,
            DesiredCapacity=capacity
        )

    def get_infra_log(self, max_items=30):
        """
        Return stack events as recorded in cloudformation
        Return:  list of (timestamp, logical-resource-idm resource-status) tuples
        """
        events = []
        paginator = self.cfn.meta.client.get_paginator("describe_stack_events")
        status = paginator.paginate(StackName=self.stack,
                                    PaginationConfig={
                                        'MaxItems': max_items
                                    })
        for event in status.search("StackEvents[*].[Timestamp, LogicalResourceId, ResourceStatus]"):
            events.append([str(e) for e in event])
        return events

    def nat_egress_ip(self):
        """
        Get the NAT-ed instances originating IP.
        Useful for whitelisting
        :return: the IP as string
        """
        vpc_id = self.__get_vpc_id()
        filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}]
        gateways = self.ec2.describe_nat_gateways(Filters=filters)
        ip = jmespath.search("NatGateways[0].NatGatewayAddresses[0].PublicIp",
                             gateways)
        return ip

    def __get_vpc_id(self):
        # TODO cache
        filters = [{ 'Name': 'tag:name', 'Values': [self.base.cell]}]
        vpcs = self.ec2.describe_vpcs(Filters=filters)
        return jmespath.search("Vpcs[0].VpcId", vpcs)


    def version(self):
        """
        Method may make calls over network
        :return: CellOS version string
        """
        # TODO (clehene) this can be cached
        all_stacks = self.list_all()
        this_stack = filter(lambda x: x[0] == self.base.cell, all_stacks)
        if len(this_stack) == 1:
            return this_stack[0][3]
        else:
            raise RuntimeError("Expecting 1 stack. Got: {} ".format(this_stack))

    def list_all(self):
        stacks = [stack for stack in jmespath.search(
            "Stacks["
            "? (Tags[? Key=='name'] && Tags[? Key=='version'] )"
            "][ StackId, StackName, StackStatus, Tags[? Key=='version'].Value | [0], CreationTime]",
            self.cfn.meta.client.describe_stacks()
        ) if not re.match(r".*(MembraneStack|NucleusStack|StatefulBodyStack|"
                          r"StatelessBodyStack|BastionStack).*", stack[0])]
        # extract region from stack id arn:aws:cloudformation:us-west-1:482993447592:stack/c1/1af7..
        stacks = [[stack[1], stack[0].split(":")[3]] + stack[2:] for stack in stacks]
        return stacks

    def list_one(self, cell):
        out = type("", (), {})()
        out.instances = type("", (), {})()
        out.instances.nucleus = self.instances("nucleus")
        out.instances.stateless = self.instances("stateless-body")
        out.instances.stateful = self.instances("stateful-body")
        out.instances.membrane = self.instances("membrane")
        out.statuspage = self.statuspage

        elbs = jmespath.search(
            "LoadBalancerDescriptions[*].[LoadBalancerName, DNSName]"
            "|[? contains([0], `{}-`) == `true`]".format(self.base.cell),
            self.elb.describe_load_balancers()
        )
        # filter ELBs for only this cell (e.g.  c1-mesos and not c1-1-mesos )
        expression = self.base.cell + "[-lb]*-(marathon|gateway|mesos|zookeeper)"
        regexp = re.compile(expression)
        out.load_balancers = filter(lambda name: regexp.match(name[0]), elbs)
        out.gateway = type("", (), {})()
        out.gateway.zookeeper = self.gateway("zookeeper")
        out.gateway.mesos = self.gateway("mesos")
        out.gateway.marathon = self.gateway("marathon")
        out.gateway.hdfs = self.gateway("hdfs")
        return out
