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
  cell mux <cell-name> [<role>]
  cell log <cell-name> [<role> <index>]
  cell cmd <cell-name> <role> <index> <command>
  cell proxy <cell-name>
  cell dcos <cell-name>
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
  SSH_USER - instances ssh login user (defaults to centos)
  SSH_TIMEOUT - ssh timeout in seconds (defaults to 5)
  SSH_OPTIONS - extra ssh options

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
from functools import partial, wraps
import json
import sys
import os
import re
import shutil
import socket
import time
import ConfigParser
import curses
import datetime

if os.name == 'posix' and sys.version_info[0] < 3:
    import subprocess32 as subprocess
else:
    import subprocess

import requests
from docopt import docopt
import boto3
import boto3.session
import jmespath
import sh
import pystache
import yaml

from awscli.formatter import TableFormatter
from awscli.table import MultiTable, Styler
from awscli.compat import six
DEFAULT_SOCKET = socket.socket
mkdir_p = sh.mkdir.bake("-p")
tar_zcf = sh.tar.bake("zcf")

# work directory
DIR = None
TMPDIR = None


def deep_merge(a, b):
    """
    Merges 2 dictionaries together;
    values in b will overwrite those in a
    """
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                deep_merge(a[key], b[key])
            elif isinstance(a[key], list) and isinstance(b[key], list):
                a[key].extend(b[key])
            else:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a

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
    if hasattr(f, 'read'):
        out = f.read()
    else:
        if '\n' not in f and os.path.exists(f):
            with open(f, 'r') as fd:
                out = fd.read()
        else:
            out = f
    return out


def tabulate(operation, data):
    """
    Formats a data structure as a table
    :param operation: the title of the table
    :param data: list or dict to print
    """
    table = MultiTable(initial_section=False,
                       column_separator='|', styler=Styler(),
                       auto_reformat=False)

    formatter = TableFormatter(type('dummy', (object,), {"color": "on", "query": None}))
    formatter.table = table
    stream = six.StringIO()
    formatter(operation, data, stream=stream)
    return stream.getvalue()


def command(args):
    return [
        kv
        for kv in args.items()
        if not kv[0].startswith('<') and not kv[0].startswith('-') and kv[1]
    ][0]


def cell_config():
    config = ConfigParser.RawConfigParser()
    config.read(os.path.expanduser('~/.aws/config'))
    config.read(os.path.expanduser('~/.cellos/config'))
    return config


def first(*args):
    for item in args:
        if item is not None:
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
            region_name=self.region,
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
            os.getenv('AWS_DEFAULT_REGION'),
            self.conf('region'),
        )

    @property
    def existing_bucket(self):
        return first(
            os.getenv('CELL_BUCKET'),
            self.conf('bucket'),
        )

    @property
    def bucket(self):
        return first(
            os.getenv('CELL_BUCKET'),
            self.conf('bucket'),
            self.full_cell
        )

    @property
    def existing_key_pair(self):
        return first(
            os.getenv('AWS_KEY_PAIR'),
            self.conf('key_pair'),
        )

    @property
    def key_path(self):
        return first(
            os.getenv("KEYPATH"),
            self.conf("keypath"),
            os.path.expanduser("~/.ssh")
        )

    @property
    def key_pair(self):
        return first(
            os.getenv('AWS_KEY_PAIR'),
            self.conf('key_pair'),
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
    def dns_name(self):
        return "gw.{cell}.metal-cell.adobe.io".format(cell=self.cell)

    @property
    def stack(self):
        return self.cell

    @property
    def proxy_port(self):
        return first(
            os.getenv('PROXY_PORT'),
            self.conf('proxy_port'),
            '1234'
        )

    @property
    def saasbase_access_key_id(self):
        return first(
            os.getenv('SAASBASE_ACCESS_KEY_ID'),
            self.conf('saasbase_access_key_id'),
            'XXXXXXXXXXXXXXXXXXXX'
        )

    @property
    def saasbase_secret_access_key(self):
        return first(
            os.getenv('SAASBASE_SECRET_ACCESS_KEY'),
            self.conf('saasbase_secret_access_key'),
            'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        )

    @property
    def ssh_user(self):
        return first(
            os.getenv('SSH_USER'),
            self.conf('ssh_user'),
            'centos'
        )

    @property
    def ssh_timeout(self):
        return first(
            os.getenv('SSH_TIMEOUT'),
            self.conf('ssh_timeout'),
            '5'
        )

    @property
    def ssh_options(self):
        return first(
            os.getenv('SSH_OPTIONS'),
            self.conf('ssh_options'),
            ''
        )

    def tmp(self, path):
        path = os.path.join(TMPDIR, self.cell, path)
        mkdir_p(os.path.dirname(path))
        return path

    @property
    def command(self):
        return command(self.arguments)[0]

    @property
    def cache_expiry_seconds(self):
        return first(
            os.getenv('CACHE_EXPIRY_SECONDS'),
            self.conf('cache_expiry_seconds'),
            60 * 3
        )

    @property
    def statuspage(self):
        # s3 endpoint is not consistent across AWS regions
        # in us-east-1 the endpoint doesn't contain the region in the url
        s3_endpoint = "s3-{region}.amazonaws.com".format(region=self.region).replace('us-east-1', 'external-1')
        return "http://{full_cell}.{s3_endpoint}/{full_cell}/shared/status/status.html".format(full_cell=self.full_cell,
                                                                                               s3_endpoint=s3_endpoint)
    def gateway(self, service):
        return "http://{}.{}".format(service, self.dns_name)

    def check_cell_exists(f):
        @wraps(f)
        def wrapped(inst, *args, **kwargs):
            try:
                # if the cell parameter is defined, check it
                if inst.cell != None:
                    inst.session.client('cloudformation').describe_stacks(StackName=inst.cell)
            except Exception:
                print "Cell {} does not exist or is not running !".format(inst.cell)
                sys.exit(1)
            return f(inst, *args, **kwargs)
        return wrapped

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
            print "CREATE bucket s3://{} in region {}".format(self.bucket, self.region)
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

        print "CORS Configuration for bucket {}".format(self.bucket)
        bucket = self.s3.Bucket(self.bucket)
        cors = bucket.Cors()
        config = {
            "CORSRules": [{
                "AllowedMethods": ["GET"],
                "AllowedOrigins": ["*"],
            }]
        }
        cors.put(CORSConfiguration=config)
        self.upload(DIR + "/deploy/aws/resources/status.html", "/shared/status/",
                    extra_args={"ContentType": "text/html"})

    def delete_bucket(self):
        if not self.existing_bucket:
            delete_response = self.s3.Bucket(self.bucket).objects.delete()
            print "DELETE s3://{}".format(self.bucket)
            self.s3.Bucket(self.bucket).delete()
        else:
            print "DELETE s3://{}/{}".format(self.bucket, self.full_cell)  # only delete bucket sub-folder
            delete_response = self.s3.Bucket(self.bucket).objects.filter(Prefix=self.full_cell).delete()
        if len(delete_response) > 0:
            for f in delete_response[0]['Deleted']:
                print "DELETE s3://{}".format(f['Key'])

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
                    - delete it (aws ec2 delete-key-pair --key-name {})
                    - try another cell name
                    - or use this key instead by setting throught AWS_KEY_PAIR
                    or in the config file
                """.format(self.key_pair, self.key_file, self.full_cell)
                raise KeyException()
            if os.path.exists(self.key_file):
                print "Local key file {} already exists".format(self.key_file)
                raise KeyException()
            print "CREATE key pair {} -> {}".format(self.key_pair, self.key_file)
            result = self.ec2.create_key_pair(
                KeyName=self.key_pair
            )
            with open(self.key_file, "wb+") as f:
                f.write(result['KeyMaterial'])
                f.flush()
            os.chmod(self.key_file, 0600)

    def delete_key(self):
        if not self.existing_key_pair:
            print "DELETE keypair {}".format(self.key_pair)
            self.ec2.delete_key_pair(KeyName=self.key_pair)
            print "DELETE key file {}".format(self.key_file)
            if os.path.isfile(self.key_file):
                os.remove(self.key_file)

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
        remote_path = self.full_cell + "/" + key
        self.s3.meta.client.upload_file(path, self.bucket, remote_path, ExtraArgs=extra_args)
        print "UPLOADED {} to s3://{}/{}".format(path, self.bucket, remote_path)

    def run_build(self):
        self.build_stack_files()
        self.build_seed()

    @check_cell_exists
    def run_seed(self):
        self.seed()

    def stack_action(self, action="create"):
        self.build_stack_files()
        self.upload(self.tmp("elastic-cell.json"), "/")
        self.upload(self.tmp("elastic-cell-scaling-group.json"), "/")
        parameters = [
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
            ]
        template_url = "https://s3.amazonaws.com/{}/{}/elastic-cell.json".format(self.bucket, self.full_cell)
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
                        'Value': self.cell
                    },
                    {
                        'Key': 'version',
                        'Value': self.version
                    },
                ]
            )
            print stack.stack_id
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


    def run_create(self):
        try:
            self.create_bucket()
        except Exception:
            traceback.print_exc(file=sys.stdout)
            sys.exit(1)
        try:
            self.create_key()
        except Exception:
            self.delete_bucket()
            traceback.print_exc(file=sys.stdout)
            sys.exit(1)
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
            sys.exit(1)
        print """
        To watch your cell infrastructure provisioning log you can
            ./cell log {cell}
        For detailed node provisioning logs
            ./cell log {cell} nucleus 1
        For detailed debugging logs, go to CloudWatch:
            https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logs:
        For detailed status (times included), navigate to
            {statuspage}

        To open external SSH access see https://inside.corp.adobe.com/itech/kc/IT00792.html
        """.format(cell=self.cell, full_cell=self.full_cell, region=self.region, statuspage=self.statuspage)

    @check_cell_exists
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
            self.delete_key()
            self.delete_bucket()
        else:
            print "Aborted deleting stack"

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

    @check_cell_exists
    def run_list(self):
        if self.cell == None:
            stacks = [stack for stack in jmespath.search(
                "Stacks["
                "? (Tags[? Key=='name'] && Tags[? Key=='version'] )"
                "][ StackId, StackName, StackStatus, Tags[? Key=='version'].Value | [0], CreationTime]",
                self.cfn.meta.client.describe_stacks()
            ) if not re.match(r".*(MembraneStack|NucleusStack|StatefulBodyStack|StatelessBodyStack).*", stack[0])]
            # extract region from stack id arn:aws:cloudformation:us-west-1:482993447592:stack/c1/1af7..
            stacks = [[stack[1], stack[0].split(":")[3]] + stack[2:] for stack in stacks]
            print tabulate("list", stacks)
        else:
            print tabulate("nucleus", self.instances("nucleus"))
            print tabulate("stateless-body", self.instances("stateless-body"))
            print tabulate("stateful-body", self.instances("stateful-body"))
            print tabulate("membrane", self.instances("membrane"))

            print "[bucket]"
            # for f in self.s3.Bucket(self.bucket).objects.filter(Prefix="{}".format(self.full_cell)):
            #     print f.key

            status_page={"status_page": self.statuspage}
            print tabulate("Status Page", status_page)

            elbs = jmespath.search(
                "LoadBalancerDescriptions[*].[LoadBalancerName, DNSName]|[? contains([0], `{}-`) == `true`]".format(self.cell, self.cell),
                self.elb.describe_load_balancers()
            )

            # filter ELBs for only this cell (e.g.  c1-mesos and not c1-1-mesos )
            expression = self.cell + "[-lb]*-(marathon|membrane|mesos|zookeeper)"
            regexp = re.compile(expression)
            elbs = filter(lambda name: regexp.match(name[0]), elbs)

            print tabulate("ELBs", elbs)

            print tabulate("Gateway", [
                ["zookeeper", self.gateway("zookeeper")],
                ["mesos", self.gateway("mesos")],
                ["marathon", self.gateway("marathon")],
                ["hdfs", self.gateway("hdfs")],
            ])

    def is_fresh_file(self, path):
        """ Checks if a file has been touched in the last X seconds """
        return os.path.exists(path) and \
             (time.time() - os.stat(path).st_mtime) < self.cache_expiry_seconds

    def ensure_cell_config(self):
        """
        Creates a cell generic configuration YAML file, containing the most
        important cell attributes:
            - zookeeper
            - mesos
            - marathon
        """
        generic_config = self.tmp("config.yaml")
        if self.is_fresh_file(generic_config):
            return
        # create cell variables
        tmp = flatten(self.instances("nucleus", format="PrivateIpAddress"))
        zk = ",".join([ip + ":2181" for ip in tmp])

        generic_config = self.tmp("config.yaml")
        with open(generic_config, "wb+") as f:
            f.write("""\
zk: {zookeeper}
mesos: {mesos}
marathon: {marathon}
cell: {cell}
            """.format(
                zookeeper=zk,
                mesos=self.gateway("mesos"),
                marathon=self.gateway("marathon"),
                cell=self.cell
            ))
            f.flush()

    def ensure_dcos_config(self):
        """
        Creates a DCOS cli configuration file
        """
        dcos_config = self.tmp("dcos.toml")
        if os.path.exists(dcos_config):
            return
        with open(dcos_config, "wb+") as f:
            f.write("""\
[core]
mesos_master_url = "{mesos}"
reporting = false
email = "cell@metal-cell.adobe.io"
cell_url = "http://{{service}}.{dns}"
[marathon]
url = "{marathon}"
[package]
sources = [ "https://s3.amazonaws.com/saasbase-repo/cell-os/cell-os-universe-{version}.zip"]
cache = "{tmp}/dcos_tmp"
                """.format(
                    mesos=self.gateway("mesos"),
                    marathon=self.gateway("marathon"),
                    version=self.version,
                    tmp=self.tmp(""),
                    dns=self.dns_name
                )
            )
            f.flush()

    def ensure_ssh_config(self):
        """
        Creates a ssh configuration file used for proxying
        """
        ssh_config = self.tmp("ssh_config")
        if self.is_fresh_file(ssh_config):
            return
        stateless_instances = flatten(self.instances(role='stateless-body', format="PublicIpAddress"))
        with open(ssh_config, "wb+") as f:
            f.write("""\
Host proxy-cell-{cell}
Hostname {host}
StrictHostKeyChecking no
IdentityFile {key}
User centos
DynamicForward {port}
            """.format(
                cell=self.cell,
                host=stateless_instances[0],
                key=self.key_file,
                port=self.proxy_port)
            )
            f.flush()

    def ensure_config(self):
        self.ensure_cell_config()
        self.ensure_dcos_config()
        self.ensure_ssh_config()

    def prepare_dcos_package_install(self, args):
        is_install = len(args) >= 2 and (args[0] == 'package' and args[1] == 'install')
        if not is_install:
            return args

        # if we have an dcos package install command, check to see if we have
        # an options file - supported package
        package = args[-1]
        if package[0:2] == "--":
            # can't find package, return
            print "Unsupported package or bad command: {}".format(" ".join(args))
            return args

        if "--cli" in args and not "--app" in args:
            print "Not using options for cli install"
            return args

        # prepare dcos packages
        # to work around for Mesos-DNS, we need to create an options file
        # for each DCOS package we install
        # this file is rendered into
        # .generated/<cell-name>/<package>_dcos_options.json
        opts_template = DIR + "/deploy/dcos/{}.json.template".format(package)
        if not os.path.exists(opts_template):
            print "Unsupported package or bad command: {}".format(str(package))
            return args

        print "Found supported package {}, rendering options file".format(package)
        opts_file = self.tmp("{}.json".format(package))
        with open(opts_file, "wb+") as outf:
            outf.write(
                pystache.render(
                    readify(opts_template),
                    yaml.load(readify(self.tmp("config.yaml")))
                )
            )
            outf.flush()
            print "Rendered DCOS config for package {}\n\t as {}".\
                format(package, opts_file)

        # try to append options to the command
        has_options = '--options' in args
        if has_options:
            print "Command already contains --options, merging options file !!!"
            cell_json = json.loads(readify(opts_file))
            opts_file_index = args.index("--options") + 1
            user_json = json.loads(readify(args[opts_file_index]))
            aggregated_json = deep_merge(dict(cell_json), user_json)
            with open(opts_file, "wb+") as outf:
                outf.write(json.dumps(aggregated_json, indent=4))
            args[opts_file_index] = opts_file
            return args

        print "Adding package install options"
        args.insert(-1, "--options=" + self.tmp("{}.json".format(package)))
        return args

    # we wrap the dcos command with the gateway configuration
    @check_cell_exists
    def run_dcos(self):
        self.ensure_config()
        dcos_args = sys.argv[3:]
        dcos_args = self.prepare_dcos_package_install(dcos_args)

        command = " ".join(["dcos"] + dcos_args)
        print "Running {}...".format(command)
        os.environ["DCOS_CONFIG"] = self.tmp("dcos.toml")
        subprocess.call(command, shell=True)

    @check_cell_exists
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

    @check_cell_exists
    def run_ssh(self, command=None):
        self.ensure_config()
        ssh_options="{} -o ConnectTimeout={}".format(self.ssh_options, self.ssh_timeout)

        instances = flatten(self.instances(self.arguments["<role>"], format="PublicIpAddress"))
        index = int(self.arguments["<index>"])
        if index is None or index == "":
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
            subprocess.call("ssh {} {}@{} -i {} {}".format(
                ssh_options, self.ssh_user, ip, self.key_file, command
            ), shell=True)
        else:
            subprocess.call("ssh {} {}@{} -i {}".format(
                ssh_options, self.ssh_user, ip, self.key_file
            ), shell=True)

    @check_cell_exists
    def run_cmd(self):
        self.run_ssh(self.arguments['<command>'])

    def get_stack_log(self, max_items=30):
        """
        Return stack events as recorded in cloudformation
        Return:  list of (timestamp, logical-resource-idm resource-status) tuples
        """
        max_items = 10
        events = []
        paginator = self.cfn.meta.client.get_paginator("describe_stack_events")
        status = paginator.paginate(StackName=self.stack,
                                    PaginationConfig={
                                        'MaxItems': max_items
                                    })
        for event in status.search("StackEvents[*].[Timestamp, LogicalResourceId, ResourceStatus]"):
            events.append([str(e) for e in event])
        return events

    def run_log(self):
        if not self.arguments["<role>"]:
            refresh_interval = 2
            def draw(stdscr):
                while True:
                    try:
                        stdscr.clear()
                        stdscr.addstr("Refreshing every {}s: {}\n"
                                .format(refresh_interval, datetime.datetime.now()))
                        status = tabulate("Stack Events", self.get_stack_log())
                        for line in status.split("\n"):
                            try:
                                stdscr.addstr("%s\n" % line)
                            except:
                                # when no space available on screen, break
                                break
                        stdscr.refresh()
                        time.sleep(refresh_interval)
                    except KeyboardInterrupt:
                        break
                    except Exception, e:
                        # any curses error should trigger a refresh
                        continue
            curses.wrapper(draw)
        else:
            self.run_ssh("tail -f -n 20 /var/log/cloud-init-output.log")

    @check_cell_exists
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

    @check_cell_exists
    def run_mux(self):
        self.ensure_config()
        if not sh.which('tmux'):
            print("You need tmux for this subcommand. Install it with brew install tmux")
            return
        if not sh.which('mux'):
            print("You need mux for this subcommand. Install it with gem install tmuxinator.")
            return

        roles = ROLES[:]
        if self.arguments["<role>"]:
            roles = [self.arguments["<role>"]]

        cfg_template = '''
name: {{cell_name}}
root: ~/

windows:
  {{#roles}}
  - {{name}}:
      layout: tiled
      panes:
        {{#instances}}
        - {{priv_ip_addr}}:
          - ssh -i {{ssh_key}} -o ConnectTimeout={{ssh_timeout}} {{ssh_options}} {{ssh_user}}@{{pub_ip_addr}}
          - clear
        {{/instances}}
  {{/roles}}
'''
        cfg = {
            'cell_name': self.full_cell,
            'ssh_key': self.key_file,
            'ssh_user': self.ssh_user,
            'ssh_timeout': self.ssh_timeout,
            'ssh_options': self.ssh_options,
            'roles': [],
        }

        for role in sorted(roles):
            cfg['roles'].append({
                'name': role,
                'instances': [{'priv_ip_addr': instance[0], 'pub_ip_addr': instance[1]}
                              for instance in self.instances(role=role, format="PrivateIpAddress, PublicIpAddress")[0]]
            })

        with open(os.path.join(os.path.expanduser('~/.tmuxinator'),
                               '{}.yml'.format(self.full_cell)), 'w') as f:
            f.write(pystache.render(cfg_template, cfg))
            f.flush()

        subprocess.call('mux {}'.format(self.full_cell), shell=True)

    @check_cell_exists
    def run_proxy(self):
        self.ensure_config()
        ssh_cmd = str(sh.ssh)
        try:
            subprocess.call("pkill -9 -f \"ssh.*proxy-cell\"", shell=True)
        except Exception:
            pass

        subprocess.call("{} -f -F {} -N proxy-cell-{} &>/dev/null".format(ssh_cmd, self.tmp("ssh_config"), self.cell), shell=True)

    def output(self, filter):
        return jmespath.search(
            "Stacks[0].Outputs | [?contains(OutputValue, `{}`) == `true`]|[0]|OutputValue".format(filter),
            self.cfn.meta.client.describe_stacks(StackName=self.stack)
        )

def main(work_dir=None):
    global DIR, TMPDIR
    DIR = os.path.dirname(os.path.realpath(__file__))
    if work_dir is None:
        work_dir = os.path.expanduser('~/.cellos')
        import pkg_resources
        version = pkg_resources.get_distribution("cellos").version
    else:
        version = readify(DIR + '/VERSION').strip()

    TMPDIR = os.path.join(work_dir, ".generated")
    mkdir_p(TMPDIR)
    # docopt hack to allow arbitrary arguments to docopt
    # necessary to call dcos subcommand
    if len(sys.argv) > 1 and sys.argv[1] == 'dcos':
        arguments = docopt(__doc__, argv=sys.argv[1:3], version=version)
    else:
        arguments = docopt(__doc__, version=version)

    if arguments["<cell-name>"] and len(arguments["<cell-name>"]) >= 22:
        print """\
<cell-name> argument must be < 22 chars long, exiting...

It is used to build an ELB name which is 32 chars max:
    http://docs.aws.amazon.com/ElasticLoadBalancing/latest/APIReference/API_CreateLoadBalancer.html
"""
        sys.exit(1)
    Cell(arguments, version).run()


if __name__ == '__main__':
    # running in dev mode,
    # set the current directory work dir
    main(os.path.dirname(os.path.realpath(__file__)))

