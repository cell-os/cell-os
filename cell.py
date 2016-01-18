#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""\

 ██████╗███████╗██╗     ██╗             ██████╗  ███████╗     ██╗   ██████╗
██╔════╝██╔════╝██║     ██║            ██╔═══██╗ ██╔════╝    ███║   ╚════██╗
██║     █████╗  ██║     ██║     █████╗ ██║   ██║ ███████╗    ╚██║    █████╔╝
██║     ██╔══╝  ██║     ██║     ╚════╝ ██║   ██║ ╚════██║     ██║   ██╔═══╝
╚██████╗███████╗███████╗██████╗        ╚██████╔╝ ███████║     ██║█╗ ███████╗
 ╚═════╝╚══════╝╚══════╝╚═════╝         ╚═════╝  ╚══════╝     ╚═╝═╝ ╚══════╝

cell-os cli ${VERSION}

Usage:
  cell build <cell-name> [--template-url <substack-template-url>]
  cell create <cell-name>
  cell update <cell-name>
  cell delete <cell-name>
  cell list [<cell-name>]
  cell scale <cell-name> <role> <capacity>
  cell ssh <cell-name> <role> <index>
  cell i2cssh <cell-name> [<role>]
  cell log <cell-name> [<role> <index>]
  cell cmd <cell-name> <role> <index> <command>
  cell proxy <cell-name>
  cell mesos <cell-name> <method> <path> [<payload>]
  cell marathon <cell-name> <method> <path> [<payload>]
  cell zk <cell-name> <method> <path> [<payload>]
  cell (-h | --help)
  cell --version

Options:
  -h --help                              Show this message.
  --version                              Show version.
  --template-url <substack-template-url> The path of the substack template to burn in the stack [default: set path to template].

Environment variables:

  AWS_KEY_PAIR - EC2 ssh keypair to use (new keypair is created otherwise)
  CELL_BUCKET - S3 bucket used  (new bucket is created otherwise)
  KEYPATH - the local path where <keypair>.pem is found (defaults to
    ${HOME}/.ssh). The .pem extension is required.
  PROXY_PORT - the SOCKS5 proxy port (defaults to ${PROXY_PORT})

All AWS CLI environment variables (e.g. AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, etc.) and configs apply.

This CLI is a convenience tool, not intended as an exhaustive cluster manager.
For advanced use-cases please use the AWS CLI or the AWS web console.

For additional help use dl-metal-cell-users@adobe.com.
For development related questions use dl-metal-cell-dev@adobe.com
Github git.corp.adobe.com/metal-cell/cell-os
Slack https://adobe.slack.com/messages/metal-cell/
"""

import binascii
import traceback
from functools import partial
import json
import sys
import os
import re
import shutil
import socket
import ConfigParser

import socks
import requests
from docopt import docopt
import boto3
import boto3.session
import jmespath
import sh

DIR = os.path.dirname(os.path.realpath(__file__))

mkdir_p = sh.mkdir.bake("-p")
tar_zcf = sh.tar.bake("zcf")

tmpdir = DIR + "/.generated"
mkdir_p(tmpdir)

DEFAULT_SOCKET = socket.socket

def flatten(l):
    """
    Flattens a list;
    Taking a list that can contain any number of nested lists, it returns a one-level list with the elements
    [a] -> [a]
    [[a]] -> [a]
    [[a, b, c], d, [[e]]] -> [a, b, c, d, e]
    """
    def _flat(l, r):
        if type(l) is not list:
            r.append(l)
        else:
            for i in l:
                r = r + flatten(i)
        return r
    return _flat(l, [])

def readify(f):
    if f is None:
        return None
    out = ""
    if hasattr(f, 'read'):
        out = f.read()
    else:
        if '\n' not in f and os.path.exists(f):
            with open(f, 'r') as fd:
                out = fd.read()
        else:
            out = f
    return out

def table_print(arr):
    if arr == None or len(arr) == 0:
        return

    headlen = len(arr[0])
    fs = "{}\t" * headlen
    for item in arr:
        print fs.format(*item)

def command(args):
    return [
        kv
        for kv in args.items()
        if not kv[0].startswith('<') and not kv[0].startswith('-') and kv[1]
    ][0]

def cell_config():
    config = ConfigParser.RawConfigParser()
    config.read(os.path.expanduser('~/.cell'))
    return config

def first(*args):
    for item in args:
        if not item is None:
            return item
    return None

def conf_get(config, profiles, key):
    for profile in profiles:
        value = None
        try:
            value = config.get(profile, key)
        except:
            pass
        if value is not None:
            return value
    return None

class KeyException(Exception):
    pass

class BucketException(Exception):
    pass

ROLES = ["nucleus", "stateless-body", "stateful-body", "membrane"]
class Cell(object):

    def __init__(self, arguments, version):
        self.version = version
        self.arguments = arguments
        self.config = cell_config()
        config_sections = ['default']
        if self.cell:
            config_sections.insert(0, self.cell)
        self.conf = partial(conf_get, self.config, config_sections)
        self.session = boto3.session.Session(
            region_name=first(
                self.conf('region'),
                os.getenv('AWS_DEFAULT_REGION')
            ),
            aws_access_key_id=self.conf('aws_access_key_id'),
            aws_secret_access_key=self.conf('aws_secret_access_key'),
        )
        self.cfn = self.session.resource('cloudformation')
        self.s3 = self.session.resource('s3')
        self.ec2 = self.session.client('ec2')
        self.elb = self.session.client('elb')
        self.asg = self.session.client('autoscaling')

    @property
    def region(self):
        return first(
            self.conf('region'),
            os.getenv('AWS_DEFAULT_REGION')
        )

    @property
    def existing_bucket(self):
        return first(
            self.conf('bucket'),
            os.getenv('CELL_BUCKET')
        )

    @property
    def bucket(self):
        return first(
            self.conf('bucket'),
            os.getenv('CELL_BUCKET'),
            self.full_cell
        )

    @property
    def existing_key_pair(self):
        return first(
            self.conf('key_pair'),
            os.getenv('AWS_KEY_PAIR')
        )

    @property
    def key_path(self):
        return first(
            self.conf("keypath"),
            os.getenv("KEYPATH"),
            os.path.expanduser("~/.ssh")
        )

    @property
    def key_pair(self):
        return first(
            self.conf('key_pair'),
            os.getenv('AWS_KEY_PAIR'),
            self.full_cell
        )

    @property
    def key_file(self):
        return "{}/{}.pem".format(self.key_path, self.key_pair)

    @property
    def full_cell(self):
        return "cell-os--{}".format(self.cell)

    @property
    def cell(self):
        return self.arguments["<cell-name>"]

    @property
    def stack(self):
        return self.cell

    @property
    def proxy_port(self):
        return first(
            self.conf('proxy_port'),
            os.getenv('PROXY_PORT'),
            '1234'
        )

    @property
    def saasbase_access_key_id(self):
        return first(
            self.conf('saasbase_access_key_id'),
            os.getenv('SAASBASE_ACCESS_KEY_ID'),
            'XXXXXXXXXXXXXXXXXXXX'
        )

    @property
    def saasbase_secret_access_key(self):
        return first(
            self.conf('saasbase_secret_access_key'),
            os.getenv('SAASBASE_SECRET_ACCESS_KEY'),
            'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        )

    @property
    def ssh_user(self):
        return first(
            self.conf('ssh_user'),
            os.getenv('SSH_USER'),
            'centos'
        )


    def tmp(self, path):
        path = os.path.join(tmpdir, self.cell, path)
        mkdir_p(os.path.dirname(path))
        return path

    @property
    def command(self):
        return command(self.arguments)[0]

    def run(self):
        getattr(self, 'run_%s' % self.command)()

    def build_stack_files(self):
        mkdir_p(DIR + "/deploy/aws/build")
        args = [DIR + "/deploy/aws/elastic-cell.py"]
        if self.arguments['--template-url']:
            args.append(self.arguments['--template-url'])
        print "Building stack ..."
        sh.python(args, _out=self.tmp("elastic-cell.json"))
        print "Building sub-stack ..."
        sh.python([DIR + "/deploy/aws/elastic-cell-scaling-group.py"], _out=self.tmp("elastic-cell-scaling-group.json"))

    def build_seed(self):
        with sh.pushd(DIR + "/deploy"):
            tar_zcf(["seed.tar.gz", "seed"])
            shutil.move(DIR + "/deploy/seed.tar.gz", self.tmp("seed.tar.gz"))

    def seed(self):
        self.build_seed()
        self.upload(self.tmp("seed.tar.gz"), "/shared/cell-os/")
        self.upload(
            "{}/cell-os-base.yaml".format(DIR),
            "/shared/cell-os/cell-os-base-{}.yaml".format(self.version)
        )

    def create_bucket(self):
        if not self.existing_bucket:
            print "CREATE bucket {} in region {}".format(self.bucket, self.region)
            self.s3.create_bucket(
                Bucket=self.bucket,
                CreateBucketConfiguration={
                    'LocationConstraint': self.region
                }
            )

    def delete_bucket(self):
        if not self.existing_bucket:
            res = self.s3.Bucket(self.bucket).objects.delete()
            if len(res) > 0:
                for f in res['Deleted']:
                    print f.Key
            self.s3.Bucket(self.bucket).delete()
        else:
            res = self.s3.Bucket(self.bucket).objects.filter(Prefix=self.full_cell).delete()
            if len(res) > 0:
                for f in res['Deleted']:
                    print f.Key

    def create_key(self):
        if not self.existing_key_pair:
            # check key
            check_result = self.ec2.describe_key_pairs()
            key_exists = len([k['KeyName'] for k in check_result['KeyPairs'] if k['KeyName'] == self.key_pair]) > 0
            if key_exists:
                print """\
                Keypair conflict.
                Trying to create {} in {}, but it already exists.
                Please:
                    - delete it
                    - try another cell name
                    - or use this key instead by setting throught AWS_KEY_PAIR
                    or in the config file
                """.format(self.key_pair, self.key_file)
                raise KeyException()
            print "CREATE key pair {}".format(self.key_pair)
            result = self.ec2.create_key_pair(
                KeyName=self.key_pair
            )
            with open(self.key_file, "wb+") as f:
                f.write(result['KeyMaterial'])
            os.chmod(self.key_file, 0600)

    def delete_key(self):
        if not self.existing_key_pair:
            print "Deleting keypair {}".format(self.key_pair)
            self.ec2.delete_key_pair(KeyName=self.key_pair)
            os.remove(self.key_file)

    def upload(self, path, key):
        if key.endswith("/"):
            key = key + os.path.basename(path)
        if key.startswith("/"):
            key = key[1:]
        self.s3.meta.client.upload_file(
            path,
            self.bucket,
            self.full_cell + "/" + key
        )

    def run_build(self):
        self.build_stack_files()
        self.build_seed()

    def run_seed(self):
        self.build_seed()
        self.seed()

    def stack_action(self, action="create"):
        self.build_stack_files()
        self.upload(self.tmp("elastic-cell.json"), "/")
        self.upload(self.tmp("elastic-cell-scaling-group.json"), "/")
        getattr(self.cfn, '{}_stack'.format(action))(
            StackName=self.stack,
            TemplateURL="https://s3.amazonaws.com/{}/{}/elastic-cell.json".format(self.bucket, self.full_cell),
            Parameters=[
                {
                    'ParameterKey': 'CellName',
                    'ParameterValue': self.cell,
                },
                {
                    'ParameterKey': 'CellOsVersionBundle',
                    'ParameterValue': "cell-os-base-{}".format(self.version),
                },
                {
                    'ParameterKey': 'KeyName',
                    'ParameterValue': self.key_pair,
                },
                {
                    'ParameterKey': 'BucketName',
                    'ParameterValue': self.bucket,
                },
                {
                    'ParameterKey': 'SaasBaseAccessKeyId',
                    'ParameterValue': self.saasbase_access_key_id,
                },
                {
                    'ParameterKey': 'SaasBaseSecretAccessKey',
                    'ParameterValue': self.saasbase_secret_access_key,
                },
            ],
            DisableRollback=True,
            Capabilities=[
                'CAPABILITY_IAM',
            ],
            Tags=[
                {
                    'Key': 'name',
                    'Value': self.cell
                },
                {
                    'Key': 'version',
                    'Value': self.version
                },
            ]
        )

    def run_create(self):
        if self.command == "create":
            try:
                self.create_bucket()
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
                sys.exit(1)
            try:
                self.create_key()
            except Exception as e:
                self.delete_bucket()
                traceback.print_exc(file=sys.stdout)
                sys.exit(1)
        try:
            self.seed()
            self.stack_action()
        except Exception as e:
            print "Error creating cell: "
            print e
            try:
                self.delete_key()
            except Exception as e:
                print "Error deleting key", e
            self.delete_bucket()
            traceback.print_exc(file=sys.stdout)
            sys.exit(1)

    def run_update(self):
        self.stack_action(action='update')

    def run_delete(self):
        print "WARNING: THIS WILL DELETE ALL RESOURCES ASSOCIATED TO {}".format(self.cell)
        print "Please enter the cell name for confirmation: "
        confirmation = raw_input(">")
        if self.cell == confirmation:
            print "Deleting stack {}".format(self.stack)
            self.cfn.meta.client.delete_stack(
                StackName=self.stack
            )
            try:
                self.delete_key()
            except:
                pass
            try:
                self.delete_bucket()
            except :
                pass
        else:
            print "Abort deleting stack"

    def instances(self, role=None, format="PublicIpAddress, PrivateIpAddress, ImageId, State.Name"):
        filters = [
            {
                'Name': 'tag:cell',
                'Values': [self.cell],
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
            "Reservations[*].Instances[*].[{}]".format(format),
            self.ec2.describe_instances(
                Filters=filters
            )
        )
        return tmp

    def run_list(self):
        if self.cell == None:
            stacks = [stack for stack in jmespath.search(
                "Stacks["
                "? (Tags[? Key=='name'] && Tags[? Key=='version'] )"
                "][ StackName, StackStatus, Tags[? Key=='version'].Value | [0], CreationTime]",
                boto3.client("cloudformation").describe_stacks()
            ) if not re.match(r".*(MembraneStack|NucleusStack|StatefulBodyStack|StatelessBodyStack).*", stack[0])]
            table_print(stacks)
        else:
            print "[load balancers]"
            elbs = jmespath.search(
                "LoadBalancerDescriptions[*].[LoadBalancerName, DNSName]|[?contains([0], `{}-lb`) == `true`]".format(self.cell),
                self.elb.describe_load_balancers()
            )
            table_print(elbs)
            print "[nucleus]"
            table_print(self.instances("nucleus")[0])
            print "[stateless-body]"
            table_print(self.instances("stateless-body")[0])
            print "[stateful-body]"
            table_print(self.instances("stateful-body")[0])
            print "[membrane]"
            table_print(self.instances("membrane")[0])
            print "[bucket]"
            for f in self.s3.Bucket(self.bucket).objects.filter(Prefix="{}".format(self.full_cell)):
                print f.key

    def run_scale(self):
        capacity = int(self.arguments['<capacity>'])
        (group, current_capacity) = jmespath.search(
            "AutoScalingGroups[? (Tags[? Key=='role' && Value=='{}'] && Tags[?Key=='cell' && Value=='{}'])].[AutoScalingGroupName, DesiredCapacity]".format(
                self.arguments['<role>'],
                self.cell
            ),
            self.asg.describe_auto_scaling_groups()
        )[0]
        if current_capacity > capacity:
            print "Scaling down {}.{} ({}) to {} IS NOT IMPLEMENTED".format(
                self.cell,
                self.arguments["<role>"],
                group,
                capacity
            )
        else:
            print "Scaling {}.{} ({}) to {}".format(
                self.cell,
                self.arguments["<role>"],
                group,
                capacity
            )
            self.asg.update_auto_scaling_group(
                AutoScalingGroupName=group,
                DesiredCapacity=capacity
            )

    def run_ssh(self, command=None):
        instances = flatten(self.instances(self.arguments["<role>"], format="PublicIpAddress"))
        index = int(self.arguments["<index>"])
        if index == None or index == "":
            index = 1
        else:
            index = int(index)
        if len(instances) < index:
            print "can't find node {} in {} yet. Is the cell fully up?".format(
                index,
                self.arguments["<role>"]
            )
            return
        ip = instances[index - 1]
        if command:
            os.system("ssh centos@{} -i {} {}".format(ip, self.key_file, command))
        else:
            os.system("ssh centos@{} -i {}".format(ip, self.key_file))

    def run_cmd(self):
        self.run_ssh(self.arguments['<command>'])

    def run_log(self):
        if not self.arguments["<role>"]:
            os.system("watch -n 1 \"aws cloudformation describe-stack-events --stack-name {} --output table --query 'StackEvents[*].[Timestamp, LogicalResourceId, ResourceStatus]' --max-items 10\"".format(self.stack))
        else:
            self.run_ssh("tail -f -n 20 /var/log/cloud-init-output.log")

    def run_i2cssh(self):
        if not sh.which('i2cssh'):
            print "You need i2cssh for this subcommand. Install it with gem install i2cssh"
            return
        roles = ROLES[:]
        if self.arguments["<role>"]:
            roles = [self.arguments["<role>"]]
        instances = []
        for role in roles:
            instances.extend(
                self.instances(role=role, format="PublicIpAddress")
            )
        instances = flatten(instances)
        machines = ",".join([d for d in instances])
        if self.key_file:
            sh.i2cssh("-d", "row", "-l", self.ssh_user, "-m", machines, "-Xi={}".format(self.key_file))

    def run_proxy(self):
        instances = flatten(self.instances(role='stateless-body', format="PublicIpAddress"))
        if self.key_file:
            if not os.path.exists(self.tmp("ssh_config")):
                with open(self.tmp("ssh_config"), "wb+") as f:
                    f.write("""\
Host proxy-cell-{}
  Hostname {}
  StrictHostKeyChecking no
  IdentityFile {}
  User centos
  DynamicForward {}
                    """.format(self.cell, instances[0], self.key_file, self.proxy_port)
                    )
                    f.flush()

            ssh_cmd = str(sh.ssh)
            try:
                sh.pkill("-9", "-f", "\"^proxy-cell.*$\"")
                sh.pkill("-9", "-f", "\".*ssh.*-N.*proxy-cell.*\"")
            except sh.ErrorReturnCode:
                pass

            os.system("{} -f -F {} -N proxy-cell-{}".format(ssh_cmd, self.tmp("ssh_config"), self.cell))

    def cluster_request(self, url, converter=lambda x: x):
        socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", int(self.proxy_port))
        socket.socket = socks.socksocket
        print "Making request to {}...".format(url)
        kwargs = {
            "method": self.arguments["<method>"],
            "url": url + "/" + self.arguments["<path>"],
            "headers": {
                "Content-Type": "application/json"
            },
        }
        data = readify(self.arguments["<payload>"])
        if data:
            kwargs['data'] = converter(data)
        response = requests.request(**kwargs)
        socket.socket = DEFAULT_SOCKET
        try:
            json_response = json.loads(response.content)
            print "Response: {}\n{}".format(
                response.status_code,
                json.dumps(
                    json_response,
                    indent=2
                )
            )
        except ValueError:
            print "Response: {}\n{}".format(
                response.status_code,
                response.content
            )

    def output(self, filter):
        return jmespath.search(
            "Stacks[0].Outputs | [?contains(OutputValue, `{}`) == `true`]|[0]|OutputValue".format(filter),
            boto3.client("cloudformation").describe_stacks(StackName=self.stack)
        )

    def run_mesos(self):
        url = self.output("lb-mesos")
        self.cluster_request(url)

    def run_zk(self):
        url = self.output("lb-zookeeper")
        self.cluster_request(url, converter=binascii.hexlify)

    def run_marathon(self):
        url = self.output("lb-marathon")
        self.cluster_request(url)

if __name__ == '__main__':
    version = readify(DIR + '/VERSION').strip()
    arguments = docopt(__doc__, version=version)
    Cell(arguments, version).run()
