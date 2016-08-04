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
  cell create <cell-name> [--backend <backend>] [--cell_config <config>]
  cell list [<cell-name>] [--backend <backend>] [--cell_config <config>]
  cell update <cell-name> [--backend <backend>] [--cell_config <config>]
  cell seed <cell-name> [--backend <backend>] [--cell_config <config>]
  cell delete <cell-name> [--backend <backend>] [--cell_config <config>]
  cell scale <cell-name> <role> <capacity> [--backend <backend>] [--cell_config <config>]
  cell log <cell-name> [<role> <index>] [--backend <backend>] [--cell_config <config>]
  cell dcos <cell-name> [--backend <backend>] [--cell_config <config>]
  cell ssh <cell-name> <role> <index> [--backend <backend>] [--cell_config <config>]
  cell i2cssh <cell-name> [<role>] [--backend <backend>] [--cell_config <config>]
  cell mux <cell-name> [<role>] [--backend <backend>] [--cell_config <config>]
  cell proxy <cell-name> [--backend <backend>] [--cell_config <config>]
  cell cmd <cell-name> <role> <index> <command> [--backend <backend>] [--cell_config <config>]
  cell build <cell-name> [--template-url <substack-template-url>] [--backend <backend>] [--cell_config <config>]
  cell (-h | --help)
  cell --version

Options:
  -h --help                              Show this message.
  --version                              Show version.
  --template-url <substack-template-url> The path of the substack template to burn in the stack [default: set path to template].
  --backend <backend> The Cell backend implementation to use
  --cell_config <config> The configuration section to read values from

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

import ConfigParser
import curses
import datetime
import decorator
import imp
import inspect
import json
import os
import requests
import sh
import shutil
import sys
import textwrap
import time
import traceback

if os.name == 'posix' and sys.version_info[0] < 3:
    import subprocess32 as subprocess
else:
    import subprocess

from docopt import docopt
import pystache
import toml
import yaml

def arity(obj, method):
    return getattr(obj.__class__, method).func_code.co_argcount - 1

mkdir_p = sh.mkdir.bake("-p")
tar_zcf = sh.tar.bake("zcf")
tar_zxf = sh.tar.bake("zxf")

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

from awscli.formatter import TableFormatter
from awscli.table import MultiTable, Styler
from awscli.compat import six

def tabulate(operation, data):
    """
    Formats a data structure as a table
    :param operation: the title of the table
    :param data: list or dict to print
    """
    if data is None:
        return ""
    table = MultiTable(initial_section=False,
                       column_separator='|', styler=Styler(),
                       auto_reformat=False)

    formatter = TableFormatter(type('dummy', (object,),
                                    {"color": "on", "query": None}))
    formatter.table = table
    stream = six.StringIO()
    formatter(operation, data, stream=stream)
    return stream.getvalue()


def first(*args):
    for item in args:
        if item is not None:
            return item
    return None


class Config(object):
    def __init__(self, raw_config, sections):
        self.__dict__["sections"] = sections
        self.__dict__["raw_config"] = raw_config

    def __getattr__(self, key, cls=None):
        return Config.conf_get(self.raw_config, self.sections, key)

    def __setattr__(self, key, value):
        raise AttributeError

    @staticmethod
    def conf_get(config, profiles, key):
        value = None
        for profile in profiles:
            try:
                value = config.get(profile, key)
            except:
                pass
        return value


def cell_config():
    config = ConfigParser.RawConfigParser()
    config.read(os.path.expanduser('~/.cellos/config'))
    return config


class Struct(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

ROLES = ["nucleus", "stateless-body", "stateful-body", "membrane"]


class Cell(object):
    def get_backend(self):
        backend_dir = "/deploy/{}/backend.py"
        imp.load_source("backend", DIR + backend_dir.format(self.backend_type))
        class_name = self.backend_type.capitalize() + "Backend"
        backend = __import__('backend', globals(), locals(), [class_name], 0)
        return getattr(backend, class_name)

    def __init__(self, arguments, version):
        self.version = version
        self.arguments = arguments
        config_sections = [self.backend_type, "default"]

        if self.arguments["--cell_config"]:
            config_sections = self.arguments["--cell_config"].split(",")
        self.config = Config(cell_config(), sections=config_sections)
        self.backend_cls = self.get_backend()
        config_args = {
            "version": self.version,
            "saasbase_access_key_id": self.saasbase_access_key_id,
            "saasbase_secret_access_key": self.saasbase_secret_access_key,
            "cell": self.cell,
            "full_cell": self.full_cell,
            "cell_dir": DIR,
            "template_url": self.arguments['--template-url'],
            "repository": self.repository
        }
        if self.cell is not None:
            config_args["key_file"] = self.key_file
            config_args["tmp_dir"] = self.tmp("")

        self.backend = self.backend_cls(self.config, Struct(**config_args))

    @property
    def backend_type(self):
        return first(self.arguments["--backend"], "aws")

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
    def proxy_port(self):
        return first(
            os.getenv('PROXY_PORT'),
            self.config.proxy_port,
            '1234'
        )

    @property
    def saasbase_access_key_id(self):
        return first(
            os.getenv('SAASBASE_ACCESS_KEY_ID'),
            self.config.saasbase_access_key_id,
            'XXXXXXXXXXXXXXXXXXXX'
        )

    @property
    def saasbase_secret_access_key(self):
        return first(
            os.getenv('SAASBASE_SECRET_ACCESS_KEY'),
            self.config.saasbase_secret_access_key,
            'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        )

    @property
    def repository(self):
        return first(
            os.getenv('REPOSITORY'),
            self.config.repository,
            's3://saasbase-repo'
        )

    @property
    def net_whitelist_url(self):
        return first(
            os.getenv('NET_WHITELIST_URL'),
            self.config.net_whitelist_url,
            'https://s3.amazonaws.com/cell-os/config/whitelist.json'
        )

    @property
    def ssh_user(self):
        return first(
            os.getenv('SSH_USER'),
            self.config.ssh_user,
            'centos'
        )

    @property
    def ssh_timeout(self):
        return first(
            os.getenv('SSH_TIMEOUT'),
            self.config.ssh_timeout,
            '5'
        )

    def tmp(self, path):
        path = os.path.join(TMPDIR, self.cell, path)
        mkdir_p(os.path.dirname(path))
        return path

    @property
    def command(self):
        def command(args):
            return [kv for kv in args.items()
                    if not kv[0].startswith('<') and
                    not kv[0].startswith('-') and kv[1]][0]
        return command(self.arguments)[0]

    @property
    def cache_expiry_seconds(self):
        return first(
            os.getenv('CACHE_EXPIRY_SECONDS'),
            self.config.cache_expiry_seconds,
            60 * 3
        )

    @decorator.decorator
    def check_cell_exists(f, *args, **kwargs):
        self = args[0]
        # if the cell parameter is defined, check it
        if self.cell != None:
            try:
                exists = self.backend.cell_exists()
            except Exception:
                exists = False
            if not exists:
                raise Exception("Cell {} does not exist or is not running !"
                                .format(self.cell))
        return f(*args, **kwargs)

    def run(self, **kwargs):
        method = getattr(self, 'run_%s' % self.command)
        if inspect.getargspec(method).keywords is not None:
            method(**kwargs)
        else:
            method()

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

    def delete_temp_dir(self):
        cell_temp_dir = self.tmp("")
        print "DELETE {} temporary directory".format(cell_temp_dir)
        if cell_temp_dir != "" \
                and os.path.exists(os.path.join(cell_temp_dir, "seed.tar.gz")):
            shutil.rmtree(cell_temp_dir)
        else:
            print "Refusing to delete directory {}. Please check contents.".format(cell_temp_dir)

    def run_build(self):
        self.build_seed()
        self.backend.build()

    @check_cell_exists
    def run_seed(self):
        self.seed()
        self.backend.seed()

    def run_create(self):
        self.seed()
        self.backend.create()
        print """
        To watch your cell infrastructure provisioning log you can
            ./cell log {cell}
        For detailed node provisioning logs
            ./cell log {cell} nucleus 1

        {backend_message}

        To open external SSH access see https://inside.corp.adobe.com/itech/kc/IT00792.html
        """.format(cell=self.cell, backend_message=self.backend.create_message())

    @check_cell_exists
    def run_update(self):
        self.backend.update()

    def run_delete(self):
        print "WARNING: THIS WILL DELETE ALL RESOURCES ASSOCIATED TO {}".format(self.cell)
        print "Please enter the cell name for confirmation: "
        confirmation = raw_input(">")
        if self.cell == confirmation:
            self.backend.delete()
            self.delete_temp_dir()
        else:
            print "Aborted deleting cell"

    @check_cell_exists
    def run_list(self):
        if self.cell is None:
            stacks = self.backend.list_all()
            print tabulate("list", stacks)
        else:
            tmp = self.backend.list_one(self.cell)
            print tabulate("nucleus", tmp.instances.nucleus)
            print tabulate("stateless-body", tmp.instances.stateless)
            print tabulate("stateful-body", tmp.instances.stateful)
            print tabulate("membrane", tmp.instances.membrane)
            print tabulate("bastion", tmp.instances.membrane)

            status_page={"status_page": tmp.statuspage}
            print tabulate("Cell Infra Provisioning Status Page", status_page)
            print tabulate("Egress IP", [self.backend.nat_egress_ip()]),
            print tabulate("Load Balancers", tmp.load_balancers)

            print tabulate("Local configuration files", [
                ["SSH key", self.tmp("{}.pem".format(self.full_cell))],
                ["SSH config", self.tmp("ssh_config")],
                ["YAML config", self.tmp("config.yaml")],
                ["DCOS config", self.tmp("dcos.toml")],
                ["DCOS cache", self.tmp("dcos_tmp")],
            ])
            print tabulate("Core Services", [
                ["zookeeper", tmp.gateway.zookeeper],
                ["mesos", tmp.gateway.mesos],
                ["marathon", tmp.gateway.marathon],
                ["hdfs", tmp.gateway.hdfs],
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
        tmp = flatten(self.backend.instances("nucleus", format="PrivateIpAddress"))
        zk = ",".join([ip + ":2181" for ip in tmp])

        generic_config = self.tmp("config.yaml")
        # FIXME: needs to be dynamic
        with open(generic_config, "wb+") as f:
            f.write("""\
zk: {zookeeper}
mesos: {mesos}
marathon: {marathon}
cell: {cell}
backend: {backend}
            """.format(
                zookeeper=zk,
                mesos=self.backend.gateway("mesos"),
                marathon=self.backend.gateway("marathon"),
                cell=self.cell,
                backend=self.backend_cls.name
            ))
            f.flush()

    def ensure_ssh_config(self):
        """
        Creates a ssh configuration file used for proxying
        """
        ssh_config = self.tmp("ssh_config")
        if self.is_fresh_file(ssh_config):
            return
        if self.backend.bastion() is not None:
            bastion = self.backend.bastion()
        else:
            raise RuntimeError("bastion not available yet")
        if self.backend.proxy() is not None:
            proxy = self.backend.proxy()
        else:
            raise RuntimeError("proxy not available yet")

        with open(ssh_config, "wb+") as f:
            f.write("""\
IdentitiesOnly yes
ConnectTimeout {timeout}
IdentityFile {key}
StrictHostKeyChecking no
User {user}

Host {ip_wildcard}
  ProxyCommand ssh -i {key} {user}@{bastion} -W %h:%p

            """.format(
                timeout=self.ssh_timeout,
                cell=self.cell,
                proxy=proxy,
                bastion=bastion,
                key=self.tmp(self.key_file),
                # FIXME (clehene) ip_wildccard should be based on subnet
                ip_wildcard="10.*",
                # FIXME (clehene) user should come from config
                user="centos"
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

    def ensure_dcos_config(self):
        """
        Creates a DCOS cli configuration file
        """
        with open(os.path.join(DIR, 'cell-os-base.yaml'), 'r') as bundle_stream:
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
    cache = "{tmp}/dcos_tmp"
                """.format(
                    mesos=self.backend.gateway("mesos"),
                    marathon=self.backend.gateway("marathon"),
                    version=self.version,
                    tmp=self.tmp(""),
                    dns=self.backend.dns_name,
                    sources=",".join('"{0}"'.format(x) for x in sources)
                )
            )
            f.flush()

    def prepare_dcos_package_install(self, args):
        is_install = len(args) >= 2 and (
        args[0] == 'package' and args[1] == 'install')
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
                    dest[k] = dest[k].replace("master.mesos:2181", "{{zk}}")
                    dest[k] = dest[k].replace("master.mesos:5050", "{{mesos}}")
                    dest[k] = dest[k].replace("master.mesos:8080", "{{marathon}}")
                    dest[k] = dest[k].replace(".marathon.mesos",
                                            ".gw.{{cell}}.metal-cell.adobe.io")
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
            outf.write(rendered_options)
            outf.flush()

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
        else:
            print "Adding package install options"
            args.insert(-1, "--options=" + self.tmp("{}.json".format(package)))

        # display the contents of the config file in its final form
        with open(options_file, "r") as inf:
            print(inf.read())

        return args


    # we wrap the dcos command with the gateway configuration
    @check_cell_exists
    def run_dcos(self, **kwargs):
        self.ensure_config()
        dcos_args = kwargs["dcos"]
        print dcos_args
        os.environ["DCOS_CONFIG"] = self.tmp("dcos.toml")
        dcos_args = self.prepare_dcos_package_install(dcos_args)

        command = " ".join(["dcos"] + dcos_args)
        print "Running {}...".format(command)

        # FIXME - because of some weird interactions (passing through the shell
        # twice), we can't use the subprocess.call([list]) form, it doesn't
        # work, and we have to quote the args for complex params
        exit(subprocess.call(" ".join(["dcos"] + ['"' + arg + '"' for arg in dcos_args]), shell=True))

    @check_cell_exists
    def run_scale(self):
        capacity = int(self.arguments['<capacity>'])
        (group, current_capacity) = self.backend.get_role_capacity(
            self.arguments['<role>']
        )
        if self.arguments['<role>'] in ['nucleus', 'stateful-body'] \
                and capacity < current_capacity:
            print textwrap.dedent("""\
                WARNING: THIS WILL SCALE DOWN THE {} GROUP FROM {} TO {} !
                Please check your current capacity / data usage to avoid data loss!
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
        self.backend.scale(self.arguments["<role>"], group, capacity)

    def ssh_cmd(self, ip, ssh_executable="ssh", extra_opts="", command=""):
        ssh_options = first(
            os.getenv('SSH_OPTIONS'),
            self.config.ssh_options,
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
        instances = flatten(self.backend.instances(
            self.arguments["<role>"], format=self.get_ssh_ip_type()))
        index = int(self.arguments["<index>"])
        if index is None or index == "":
            index = 1
        else:
            index = int(index)
        if len(instances) < index:
            print("can't find node {} in {} yet. Is the cell fully up?".format(
                index, self.arguments["<role>"]
            ))
            return
        ip = instances[index - 1]
        if command:
            subprocess.call(self.ssh_cmd(ip, extra_opts="-t", command=command), shell=True)
        else:
            subprocess.call(self.ssh_cmd(ip), shell=True)

    def get_ssh_ip_type(self):
        """
        Helper method to deal with backwards compatiblity
        Note that this is used for the format argument of the instances method
         which is only used for AWS.
        """
        if self.backend.version() > "1.2.0":
            return "PrivateIpAddress"
        else:
            return "PublicIpAddress"

    @check_cell_exists
    def run_cmd(self):
        self.run_ssh(command=self.arguments['<command>'])

    def run_log(self):
        if not self.arguments["<role>"]:
            refresh_interval = 2

            def draw(stdscr):
                while True:
                    try:
                        stdscr.clear()
                        stdscr.addstr("Refreshing every {}s: {}\n"
                                .format(refresh_interval, datetime.datetime.now()))
                        status = tabulate("Stack Events", self.backend.get_infra_log())
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
                    except Exception as e:
                        # any curses error should trigger a refresh
                        continue
            curses.wrapper(draw)
        else:
            self.run_ssh("tail -f -n 20 /var/log/cloud-init-output.log")

    @check_cell_exists
    def run_i2cssh(self):
        self.ensure_config()
        if not sh.which('i2cssh'):
            print("You need i2cssh for this subcommand (gem install i2cssh)")
            return
        roles = ROLES[:]
        if self.arguments["<role>"]:
            roles = [self.arguments["<role>"]]
        instances = []
        for role in roles:
            instances_for_role = self.backend.instances(
                role=role,format=self.get_ssh_ip_type())
            if instances_for_role is not None:
                instances.extend(instances_for_role)
        instances = flatten(instances)
        machines = ",".join([d for d in instances])
        if self.key_file:
            sh.i2cssh("-d", "row", "-l", self.ssh_user, "-m", machines,
                    "-XF={}".format(self.tmp('ssh_config')))

    @check_cell_exists
    def run_mux(self):
        self.ensure_config()
        if not sh.which('tmux'):
            print("You need tmux for this subcommand (brew install tmux).")
            return
        if not sh.which('mux'):
            print("You need mux for this subcommand (gem install tmuxinator).")
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
        - {{ip_addr}}:
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
            print("ROLE: {}".format(role))
            print(self.backend.instances(role=role, format=self.get_ssh_ip_type()))
            cfg['roles'].append({
                'name': role,
                'instances': [
                    {
                        'ip_addr': instance[0],
                        'ssh_cmd': self.ssh_cmd(instance[0]),
                    }
                    for instance in self.backend.instances(role=role, format=self.get_ssh_ip_type())
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

        logfile = self.tmp("proxy.log")
        proxy = self.backend.proxy()
        cmd = self.ssh_cmd(proxy,
                           extra_opts="-f -N -D{}".format(self.proxy_port),
                           command="&>{}".format(logfile))
        print cmd
        try:
            subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            print "Proxy running on localhost:{}".format(self.proxy_port)
            print "ssh config loaded from {}".format(self.tmp(""))
        except subprocess.CalledProcessError as err:
            print "Failed to create proxy. See log at {}".format(logfile)
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
        args_to_pass = sys.argv[1:3]
        rest_args = sys.argv[3:]
        idx = 0
        while idx < len(rest_args):
            arg = rest_args[idx]
            if arg == "--backend" or arg == "--cell_config":
                args_to_pass.append(rest_args.pop(idx))
                args_to_pass.append(rest_args.pop(idx))
            else:
                idx = idx + 1
        arguments = docopt(__doc__, argv=args_to_pass, version=version)
    else:
        rest_args = []
        arguments = docopt(__doc__, version=version)

    if arguments["<cell-name>"] and len(arguments["<cell-name>"]) >= 22:
        print """\
<cell-name> argument must be < 22 chars long, exiting...
It is used to build other resource names (e.g. ELB name is 32 chars max)
"""
        sys.exit(1)
    cell = Cell(arguments, version)
    try:
        cell.run(dcos=rest_args)
    except Exception as e:
        print "{}: {}".format(cell.command, e)
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)

if __name__ == '__main__':
    # running in dev mode,
    # set the current directory work dir
    main(os.path.dirname(os.path.realpath(__file__)))

