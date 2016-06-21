#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""\

 ██████╗███████╗██╗     ██╗             ██████╗  ███████╗     ██╗   ██████╗
██╔════╝██╔════╝██║     ██║            ██╔═══██╗ ██╔════╝    ███║   ╚════██╗
██║     █████╗  ██║     ██║     █████╗ ██║   ██║ ███████╗    ╚██║    █████╔╝
██║     ██╔══╝  ██║     ██║     ╚════╝ ██║   ██║ ╚════██║     ██║   ██╔═══╝
╚██████╗███████╗███████╗██████╗        ╚██████╔╝ ███████║     ██║█╗ ███████╗
 ╚═════╝╚══════╝╚══════╝╚═════╝         ╚═════╝  ╚══════╝     ╚═╝═╝ ╚══════╝

Usage:
  cell create <cell-name>
  cell list [<cell-name>]
  cell update <cell-name>
  cell seed <cell-name>
  cell delete <cell-name>
  cell scale <cell-name> <role> <capacity>
  cell log <cell-name> [<role> <index>]
  cell dcos <cell-name>
  cell ssh <cell-name> <role> <index>
  cell i2cssh <cell-name> [<role>]
  cell mux <cell-name> [<role>]
  cell proxy <cell-name>
  cell cmd <cell-name> <role> <index> <command>
  cell build <cell-name> [--template-url <substack-template-url>]
  cell (-h | --help)
  cell --version

Options:
  -h --help                              Show this message.
  --version                              Show version.
  --template-url <substack-template-url> The path of the substack template to burn in the stack [default: set path to template].

Environment variables:

  CELL_BUCKET - S3 bucket used  (new bucket is created otherwise)
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

import traceback
from functools import partial, wraps
import json
import sys
import os
import re
import shutil
import time
import ConfigParser
import curses
import datetime
import textwrap

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
import toml
import yaml

from awscli.formatter import TableFormatter
from awscli.table import MultiTable, Styler
from awscli.compat import six
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


def readify(path):
    """

    :param path:
    :return: the content of the file or URL identified at the given path
    """
    if path is None:
        out = None
    elif hasattr(path, 'read'):
        out = path.read()
    elif '\n' not in path and os.path.exists(path):
        with open(path, 'r') as fd:
            out = fd.read()
    elif isinstance(path, basestring) \
            and (path.startswith("http://") or path.startswith("https://")):
        try:
            r = requests.get(path)
            if r.status_code != 200:
                sys.stderr.write("ERROR: downloading config file from {} ({})"
                                 .format(path, r.status_code))
            out = r.text
        except Exception as e:
            sys.stderr.write("Error while getting {}: \n\t{}".format(path, e))
            out = None
    else:
        # (clehene) why would we set the output to the input?
        out = path
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

    formatter = TableFormatter(type('dummy', (object,),
                                    {"color": "on", "query": None}))
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
    def key_file(self):
        return self.tmp("{}.pem".format(self.full_cell))

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
    def repository(self):
        return first(
            os.getenv('REPOSITORY'),
            self.conf('repository'),
            's3://saasbase-repo'
        )

    @property
    def net_whitelist_url(self):
        return first(
            os.getenv('NET_WHITELIST_URL'),
            self.conf('net_whitelist_url'),
            'https://s3.amazonaws.com/cell-os/config/whitelist.json'
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
        return "http://{full_cell}.{s3_endpoint}/{full_cell}/shared/status/status.html".format(
            full_cell=self.full_cell,
            s3_endpoint=s3_endpoint
        )

    def gateway(self, service):
        return "http://{}.{}".format(service, self.dns_name)

    def check_cell_exists(f):
        @wraps(f)
        def wrapped(inst, *args, **kwargs):
            try:
                # if the cell parameter is defined, check it
                if inst.cell is not None:
                    inst.session.client('cloudformation')\
                        .describe_stacks(StackName=inst.cell)
            except Exception:
                raise Exception("Cell {} does not exist or is not running !"
                                .format(inst.cell))
            return f(inst, *args, **kwargs)
        return wrapped

    def run(self):
        getattr(self, 'run_%s' % self.command)()

    def build_stack_files(self):
        mkdir_p(DIR + "/deploy/aws/build/config")

        args = [DIR + "/deploy/aws/elastic-cell.py"]
        if self.arguments['--template-url']:
            args += ["--template-url", self.arguments["--template-url"]]
        args += ["--net-whitelist", self.tmp("net-whitelist.json")]
        print "Building stack ..."
        sh.python(args, _out=self.tmp("elastic-cell.json"))
        print "Building sub-stack ..."
        sh.python([DIR + "/deploy/aws/elastic-cell-scaling-group.py"], _out=self.tmp("elastic-cell-scaling-group.json"))

    def build_seed_config(self):
        def parse_nets_json(json_text):
            return [
                {"addr": entry["net_address"], "mask": entry["net_mask"]}
                for entry in json.loads(json_text)["networks"]
            ]

        json_text = first(
            readify(self.net_whitelist_url),
            readify(DIR + "/deploy/config/net-whitelist.json")
        )
        entries = parse_nets_json(json_text)
        if len(entries) == 0:
            raise Exception(textwrap.dedent("""
            Empty networks whitelist file, cannot continue !
            Please check the user guide on how to create it.
            """))

        with open(self.tmp("net-whitelist.json"), "wb+") as f:
            f.write(json.dumps(entries, indent=4))
        shutil.copyfile(
            self.tmp("net-whitelist.json"),
            self.tmp("seed/config/net-whitelist.json")
        )

    def build_seed(self):
        shutil.rmtree(self.tmp("seed"), ignore_errors=True)
        shutil.copytree(DIR + "/deploy/seed", self.tmp("seed"))
        self.build_seed_config()
        with sh.pushd(self.tmp("")):
            tar_zcf(["seed.tar.gz", "seed"])
        shutil.rmtree(self.tmp("seed"))

    def seed(self):
        self.build_seed()
        self.upload(self.tmp("seed.tar.gz"), "/shared/cell-os/")
        self.upload(
            "{}/cell-os-base.yaml".format(DIR),
            "/shared/cell-os/cell-os-base-{}.yaml".format(self.version)
        )
        self.upload(DIR + "/deploy/aws/resources/status.html", "/shared/status/",
                    extra_args={"ContentType": "text/html"})
        self.upload(DIR + "/deploy/machine/user-data", "/shared/cell-os/")

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

        bucket = self.s3.Bucket(self.bucket)
        cors = bucket.Cors()
        config = {
            "CORSRules": [{
                "AllowedMethods": ["GET"],
                "AllowedOrigins": ["*"],
            }]
        }
        cors.put(CORSConfiguration=config)

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

    def create_temp_dir(self):
        mkdir_p(os.path.dirname(self.tmp("")))

    def delete_temp_dir(self, force=False):
        cell_temp_dir = self.tmp("")
        print "DELETE {} temporary directory".format(cell_temp_dir)
        if cell_temp_dir != "" \
                and (os.path.exists(os.path.join(cell_temp_dir, "seed.tar.gz"))
                     or force):
            shutil.rmtree(cell_temp_dir)
        else:
            print "Refusing to delete directory {}. Please check contents.".format(cell_temp_dir)

    def create_key(self):
        # check key
        check_result = self.ec2.describe_key_pairs()
        key_exists = len([k['KeyName'] for k in check_result['KeyPairs'] if k['KeyName'] == self.full_cell]) > 0
        if key_exists:
            print """\
            Keypair conflict.
            Trying to create {} in {}, but it already exists.
            Please:
                - delete it (aws ec2 delete-key-pair --key-name {})
                - try another cell name
            """.format(self.full_cell, self.key_file, self.full_cell)
            raise KeyException()
        print "CREATE key pair {} -> {}".format(self.full_cell, self.key_file)
        result = self.ec2.create_key_pair(
            KeyName=self.full_cell
        )
        with open(self.key_file, "wb+") as f:
            f.write(result['KeyMaterial'])
            f.flush()
        os.chmod(self.key_file, 0600)

    def delete_key(self):
        print "DELETE keypair {}".format(self.full_cell)
        self.ec2.delete_key_pair(KeyName=self.full_cell)

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
        self.build_seed()
        self.build_stack_files()

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
                    'ParameterKey': 'Repository',
                    'ParameterValue': self.repository,
                },
                {
                    'ParameterKey': 'KeyName',
                    'ParameterValue': self.full_cell,
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
            raise
        try:
            self.create_temp_dir()
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
                self.delete_temp_dir(force=True)
            except Exception as e:
                print "Error deleting local dir {}".format(self.tmp("")), e
            try:
                self.delete_key()
            except Exception as e:
                print "Error deleting key", e
            self.delete_bucket()
            traceback.print_exc(file=sys.stdout)
            raise
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
        self.seed()
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
            self.delete_temp_dir()
        else:
            print "Aborted deleting cell"

    def instances(self, role=None, format="PublicIpAddress, PrivateIpAddress, InstanceId, ImageId, State.Name"):
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
                "LoadBalancerDescriptions[*].[LoadBalancerName, DNSName]"
                "|[? contains([0], `{}-`) == `true`]".format(self.cell),
                self.elb.describe_load_balancers()
            )

            # filter ELBs for only this cell (e.g.  c1-mesos and not c1-1-mesos )
            expression = self.cell + "[-lb]*-(marathon|gateway|mesos|zookeeper)"
            regexp = re.compile(expression)
            elbs = filter(lambda name: regexp.match(name[0]), elbs)

            print tabulate("ELBs", elbs)

            print tabulate("Local configuration files", [
                ["SSH key", self.tmp("{}.pem".format(self.full_cell))],
                ["SSH config", self.tmp("ssh_config")],
                ["YAML config", self.tmp("config.yaml")],
                ["DCOS config", self.tmp("dcos.toml")],
                ["DCOS cache", self.tmp("dcos_tmp")],
            ])
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
        with open('cell-os-base.yaml', 'r') as bundle_stream:
            version_bundle = yaml.load(bundle_stream)
            universe_version =  version_bundle['cell-os-universe::version']

        repo_url = self.repository.replace('s3://', 'https://s3.amazonaws.com/')
        cell_universe_url = '{0}/cell-os/cell-os-universe-{1}.zip'\
            .format(repo_url, universe_version)
        dcos_config_file = self.tmp('dcos.toml')

        try:
            with open(dcos_config_file, 'r') as dcos_config_stream:
                dcos_config = toml.loads(dcos_config_stream.read())
                sources = dcos_config['package']['sources']
        except Exception:
            sources = [cell_universe_url]
            print('generating {config_file} with default sources {default_src}'
              .format(config_file=dcos_config_file, default_src=sources))

        # Override cell-os-universe source with the bundle version
        for index, repo in enumerate(sources):
            if 'cell-os/cell-os-universe' in repo:
                sources[index] = cell_universe_url
                break
        with open(dcos_config_file, "wb+") as f:
            f.write("""\
[core]
mesos_master_url = "{mesos}"
reporting = false
email = "cell@metal-cell.adobe.io"
cell_url = "http://{{service}}.{dns}"
[marathon]
url = "{marathon}"
[package]
sources = [{sources}]
cache = "{tmp}dcos_tmp"
                """.format(
                    mesos=self.gateway("mesos"),
                    marathon=self.gateway("marathon"),
                    tmp=self.tmp(""),
                    dns=self.dns_name,
                    sources=",".join('"{0}"'.format(x) for x in sources)
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
IdentitiesOnly yes
ConnectTimeout {timeout}
IdentityFile {key}
StrictHostKeyChecking no
User centos

Host proxy-cell-{cell}
Hostname {host}
DynamicForward {port}
            """.format(
                timeout=self.ssh_timeout,
                cell=self.cell,
                host=stateless_instances[0],
                key=self.tmp(self.key_file),
                port=self.proxy_port
            ))
            f.flush()

    def ensure_migrated(self):
        """
        1.2.0 to 1.2.1 breaking ssh key change
        FIXME: delete this in 1.3.0 timeframe, after ensuring clients migrate
        """
        for key_dir in [os.path.expanduser("~/.ssh/"), os.getenv("KEYPATH")]:
            if key_dir != None:
                old_key_file = os.path.join(key_dir, "{}.pem".format(self.full_cell))
                new_key_file = self.tmp("{}.pem".format(self.full_cell))
                if os.path.exists(old_key_file) and not os.path.exists(new_key_file):
                    print "WARN: Migrating key file from {} to {}".format(
                        old_key_file,
                        new_key_file
                    )
                    shutil.move(old_key_file, new_key_file)
                    os.chmod(new_key_file, 0400)

    def ensure_config(self):
        self.ensure_cell_config()
        self.ensure_dcos_config()
        self.ensure_ssh_config()
        self.ensure_migrated()

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

        # DCOS can describe a package configuration schema, with default values
        # Take it and recreate an actual configuration out of it
        pkg_config = json.loads(
            subprocess.check_output(
                "dcos package describe --config {}".format(package), shell=True
            )
        )

        def config_remapper(src):
            """
            Parses a DCOS configuration specification (config.json) and outputs a
            tree with the templated configuration pieces
            Example: https://github.com/mesosphere/universe/blob/version-2.x/repo/packages/K/kafka/3/config.json
            """
            dest = {}
            for k, v in src["properties"].iteritems():
                if v["type"] == "object":
                    tmp = config_remapper(v)
                    if len(tmp) > 0:
                        dest[k] = tmp
                elif v["type"] == "string" and "default" in v:
                    dest[k] = v["default"]
                    # monkey-patch to enable general DCOS universe repo
                    # replace DCOS specific host:port service discriminators
                    # with the cell-os specific endpoints
                    # note that this works for 90% of the packages, as some
                    # may have these values hardcoded somewhere else
                    dest[k] = dest[k].replace("master.mesos:2181", "{{zk}}")
                    dest[k] = dest[k].replace("master.mesos:5050", "{{mesos}}")
                    dest[k] = dest[k].replace("master.mesos:8080",
                                              "{{marathon}}")
                    dest[k] = dest[k].replace(".marathon.mesos", self.dns_name)
            return dest

        opts_template = None
        template = config_remapper(pkg_config)
        if len(template) > 0:
            opts_template = self.tmp("{}.json.template".format(package))
            with open(opts_template, "wb+") as tf:
                tf.write(json.dumps(template, indent=4))

        if opts_template == None or not os.path.exists(opts_template):
            print "Unsupported package or bad command: {}".format(str(package))
            return args

        print "Found supported package {}, rendering options file".format(package)
        options_file = self.tmp("{}.json".format(package))
        with open(options_file, "wb+") as outf:
            rendered_options = pystache.render(
                readify(opts_template),
                yaml.load(readify(self.tmp("config.yaml")))
            )
            print("Rendered options {}".format(options_file))
            print(rendered_options)
            outf.write(rendered_options)
            outf.flush()
            print "Rendered DCOS config for package {}\n\t as {}".\
                format(package, options_file)

        # try to append options to the command
        has_options = '--options' in args
        if has_options:
            print "Command already contains --options, merging options file !!!"
            cell_json = json.loads(readify(options_file))
            opts_file_index = args.index("--options") + 1
            user_json = json.loads(readify(args[opts_file_index]))
            aggregated_json = deep_merge(dict(cell_json), user_json)
            with open(options_file, "wb+") as outf:
                outf.write(json.dumps(aggregated_json, indent=4))
            args[opts_file_index] = options_file
            return args

        print "Adding package install options"
        args.insert(-1, "--options=" + self.tmp("{}.json".format(package)))
        return args

    # we wrap the dcos command with the gateway configuration
    @check_cell_exists
    def run_dcos(self):
        self.ensure_config()
        dcos_args = sys.argv[3:]
        os.environ["DCOS_CONFIG"] = self.tmp("dcos.toml")
        dcos_args = self.prepare_dcos_package_install(dcos_args)

        command = " ".join(["dcos"] + dcos_args)
        print "Running {}...".format(command)
        # FIXME - because of some weird interactions (passing through the shell
        # twice), we can't use the subprocess.call([list]) form, it doesn't
        # work, and we have to quote the args for complex params
        subprocess.call(" ".join(["dcos"] + ['"' + arg + '"' for arg in dcos_args]), shell=True)

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
        if self.arguments['<role>'] in ['nucleus', 'stateful-body'] and capacity < current_capacity:
            print textwrap.dedent("""\
                WARNING: THIS WILL SCALE DOWN THE {} GROUP FROM {} TO {} !
                Please check your current capacity / data usage to avoid data loss !
            """).format(self.arguments["<role>"], current_capacity, capacity)
            print "Are you sure ? (y/N)"
            confirmation = raw_input(">")
            if confirmation.lower() not in ['y', 'yes']:
                print "Aborting scale down operation"
                raise Exception("Expecting 'y' or 'yes'")
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

    def ssh_cmd(self, ip, ssh_executable="ssh", extra_opts="", command=""):
        ssh_options = first(
            os.getenv('SSH_OPTIONS'),
            self.conf('ssh_options'),
            ''
        )

        return "{executable} -F {ssh_config} {opts} {host} {extra}".format(
            executable=ssh_executable,
            ssh_config=self.tmp("ssh_config"),
            opts=ssh_options + " " + extra_opts,
            host=ip,
            extra=command
        )

    @check_cell_exists
    def run_ssh(self, command=None):
        self.ensure_config()

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
            subprocess.call(self.ssh_cmd(ip, extra_opts="-t", command=command), shell=True)
        else:
            subprocess.call(self.ssh_cmd(ip), shell=True)

    @check_cell_exists
    def run_cmd(self):
        self.run_ssh(command=self.arguments['<command>'])

    def get_stack_log(self, max_items=30):
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
        self.ensure_config()
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
            sh.i2cssh("-d", "row", "-l", self.ssh_user, "-m", machines,
                    "-XF={}".format(self.tmp('ssh_config')))

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
          - {{ssh_cmd}}
          - clear
        {{/instances}}
  {{/roles}}
'''
        cfg = {
            'cell_name': self.full_cell,
            'roles': [],
        }

        for role in sorted(roles):
            cfg['roles'].append({
                'name': role,
                'instances': [
                    {'priv_ip_addr': instance[0],
                     'pub_ip_addr': instance[1],
                     'ssh_cmd': self.ssh_cmd(instance[1])
                    }
                    for instance in self.instances(role=role, format="PrivateIpAddress, PublicIpAddress")[0]
                ]
            })

        with open(os.path.join(os.path.expanduser('~/.tmuxinator'),
                               '{}.yml'.format(self.full_cell)), 'w') as f:
            f.write(pystache.render(cfg_template, cfg))
            f.flush()

        subprocess.call('mux {}'.format(self.full_cell), shell=True)

    @check_cell_exists
    def run_proxy(self):
        self.ensure_config()
        try:
            subprocess.call("pkill -9 -f \"ssh.*proxy-cell\"", shell=True)
        except Exception:
            pass

        cmd = self.ssh_cmd("proxy-cell-{}".format(self.cell), extra_opts="-f -N",
                           command="&>{}".format(self.tmp("proxy.log")))
        try:
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            print "Proxy running on localhost:{}".format(self.proxy_port)
            print "ssh config loaded from {}".format(self.tmp(""))
        except subprocess.CalledProcessError as err:
            print "Failed to create proxy"
            print err.output

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
    cell = Cell(arguments, version)
    try:
        cell.run()
    except Exception as e:
        print "{}: {}".format(cell.command, e)
        sys.exit(1)


if __name__ == '__main__':
    # running in dev mode,
    # set the current directory work dir
    main(os.path.dirname(os.path.realpath(__file__)))

