from collections import OrderedDict
import os
import re
import string
import json

import awacs
import awacs.ec2
import awacs.aws
import awacs.sts
import awacs.s3
import awacs.sqs
import awacs.autoscaling
import awacs.cloudformation
import awacs.cloudfront
import awacs.cloudwatch
import awacs.dynamodb
import awacs.elasticloadbalancing
import awacs.iam

from troposphere import Template as TropoTemplate
from troposphere import FindInMap, Output, AWSObject, Ref, Parameter, Base64, Join, awsencode
import troposphere.ec2 as ec2
import troposphere.iam as iam
import troposphere.elasticloadbalancing as elb

DNS_SUFFIXES = {
    'eu-west-1': 'eu-west-1.compute.internal',
    'us-east-1': 'ec2.internal',
}

DISKS_PER_INSTANCE_TYPE = {
    't2.micro': 0,
    't2.small': 0,
    't2.medium': 0,
    't2.large': 0,
    'm4.large': 0,
    'm4.xlarge': 0,
    'm4.2xlarge': 0,
    'm4.4xlarge': 0,
    'm4.10xlarge': 0,
    'c4.large': 0,
    'c4.xlarge': 0,
    'c4.2xlarge': 0,
    'c4.4xlarge': 0,
    'c4.8xlarge': 0,
    'g2.2xlarge': 1,
    'g2.8xlarge': 2,
    'r3.large': 1,
    'r3.xlarge': 1,
    'r3.2xlarge': 1,
    'r3.4xlarge': 1,
    'r3.8xlarge': 2,
    'i2.xlarge': 1,
    'i2.2xlarge': 2,
    'i2.4xlarge': 4,
    'i2.8xlarge': 8,
    'd2.xlarge': 3,
    'd2.2xlarge': 6,
    'd2.4xlarge': 12,
    'd2.8xlarge': 24,
    'm3.medium': 1,
    'm3.large': 1,
    'm3.xlarge': 2,
    'm3.2xlarge': 2,
    'c3.large': 2,
    'c3.xlarge': 2,
    'c3.2xlarge': 2,
    'c3.4xlarge': 2,
    'c3.8xlarge': 2,
    'm1.small': 1,
    'm1.medium': 1,
    'm1.large': 2,
    'm1.xlarge': 4,
    'c1.medium': 1,
    'c1.xlarge': 4,
    'cc2.8xlarge': 4,
    'cg1.4xlarge': 2,
    'm2.xlarge': 1,
    'm2.2xlarge': 1,
    'm2.4xlarge': 2,
    'cr1.8xlarge': 2,
    'hi1.4xlarge': 2,
    'hs1.8xlarge': 24,
    't1.micro': 0,
}

class Template(TropoTemplate):
    def __init__(self):
        TropoTemplate.__init__(self)
        self.ordered_resources = OrderedDict()
        self.metadata = OrderedDict()
        self.conditions = OrderedDict()
        self.mappings = OrderedDict()
        self.outputs = OrderedDict()
        self.parameters = OrderedDict()
        self.resources = OrderedDict()

    def iref(self, key, val=None):
        if key not in self.parameters:
            if val:
                self.parameters[key] = Parameter(key, Type='String', Default=val)
            else:
                self.parameters[key] = Parameter(key, Type='String')
        return Ref(self.parameters[key])

    def imap(self, mapping, key_lvl1, key_lvl2, val):
        if mapping not in self.mappings:
            self.mappings[mapping] = {}
        if key_lvl1 not in self.mappings[mapping]:
            self.mappings[mapping][key_lvl1] = {}
        self.mappings[mapping][key_lvl1][key_lvl2] = val
        return FindInMap(mapping, key_lvl1, key_lvl2)

    def __iadd__(self, other):
        if isinstance(other, Output):
            self.add_output(other)
        elif isinstance(other, Parameter):
            self.add_parameter(other)
        elif isinstance(other, Condition):
            self.add_condition(other)
        elif isinstance(other, AWSObject):
            self.add_resource(other)
            self.ordered_resources[other.title] = other

        return self

    def find(self, needle, first=True):
        out = []
        for k, v in self.ordered_resources.iteritems():
            if type(needle) != str and isinstance(v, needle):
                out.append(v)
            elif type(needle) == str and re.match(needle, v.title):
                out.append(v)
        if first and len(out) == 1:
            return out[0]
        return out

    def to_json(self, indent=4, sort_keys=False, separators=(',', ': ')):
        t = OrderedDict()
        if self.version:
            t['AWSTemplateFormatVersion'] = self.version
        if self.description:
            t['Description'] = self.description
        if self.parameters:
            t['Parameters'] = self.parameters
        if self.metadata:
            t['Metadata'] = self.metadata
        if self.conditions:
            t['Conditions'] = self.conditions
        if self.mappings:
            t['Mappings'] = self.mappings
        if self.outputs:
            t['Outputs'] = self.outputs
        t['Resources'] = self.resources
        return json.dumps(t, cls=awsencode, indent=indent, separators=separators)

class T(string.Template):
    delimiter = '%'
    idpattern = r'[a-z][_a-z0-9]*'

def readify(f):
    out = ""
    if hasattr(f, 'read'):
        out = f.read()
    else:
        if not('\n' in f) and os.path.exists(f):
            with open(f, 'r') as fd:
                out = fd.read()
        else:
            out = f
    return out

def network_acls(name, inp):
    acl_spec = readify(inp)

    acl_entries = []
    for line in acl_spec.splitlines():
        if not line or line.startswith('#'):
            continue
        pieces = re.split('\s+', line)
        if len(pieces) < 7:
            continue
        acl_props = {
            'NetworkAclId': Ref(name),
            'RuleNumber': pieces[1],
            'Protocol': pieces[2],
            'RuleAction': pieces[3],
            'CidrBlock': pieces[4],
            'Egress': pieces[6]
        }
        if pieces[5] != '-':
            port_range = pieces[5].split(':')
            acl_props['PortRange'] = ec2.PortRange(From=port_range[0], To=port_range[1])
        if len(pieces) > 7:
            icmp = pieces[7].split(':')
            acl_props['Icmp'] = ec2.ICMP(Code=int(icmp[0]), Type=int(icmp[1]))
        acl_entries.append(ec2.NetworkAclEntry('%s%sEntry' % (pieces[0], name), **acl_props))
    return acl_entries

def security_group_rules(inp):
    ingress = []
    egress = []
    sg_spec = readify(inp)
    for line in sg_spec.splitlines():
        if not line or line.startswith('#') or line.strip() == "":
            continue
        pieces = re.split('\s+', line)
        port_range = pieces[3].split(':')
        kwargs = {
            "FromPort": int(port_range[0]),
            "ToPort": int(port_range[1]),
            "IpProtocol": pieces[2]
        }
        if re.match(r'^[0-9\.\/]*$', pieces[1]):
            kwargs["CidrIp"] = pieces[1]
        else:
            if pieces[0] == 'ingress':
                kwargs["SourceSecurityGroupId"] = Ref(pieces[1])
            else:
                kwargs["DestinationSecurityGroupId"] = Ref(pieces[1])

        sgr = ec2.SecurityGroupRule(**kwargs)
        if pieces[0] == 'ingress':
            ingress.append(sgr)
        elif pieces[0] == 'egress':
            egress.append(sgr)
    return (ingress, egress)

def substitute(inp, substitutions={}):
    inp = readify(inp)
    out = T(inp).substitute(**substitutions)
    return out

def security_group(name, inp, vpc, substitutions={}, description=""):
    inp = readify(inp)
    ingress, egress = security_group_rules(substitute(inp, substitutions))

    if description == "":
        description = name

    return ec2.SecurityGroup(
        name,
        GroupDescription=description,
        SecurityGroupEgress=egress,
        SecurityGroupIngress=ingress,
        VpcId=Ref(vpc)
    )

def name_zone(start, i = None, az_i = None):
    id_piece = ""
    az_piece = ""
    if i is not None:
        id_piece = "%d" % i
    if az_i != None:
        az_piece = "AZ%d" % az_i
    return "%s%s%s" % (start, id_piece, az_piece)

def net_name(prefix, what, i = None, az_i = None):
    return name_zone(prefix + what, i, az_i)

def subnet_name(prefix, i = None, az_i = None):
    return net_name(prefix, "Subnet", i, az_i)

def route_table_name(prefix, i = None, az_i = None):
    return net_name(prefix, "RouteTable", i, az_i)

def route_name(prefix, i = None, az_i = None):
    return net_name(prefix, "Route", i, az_i)

def split_content(s, fixrefs=True):
    pattern = r'(Ref\([a-zA-Z0-9:]*\))'
    lines = [l + "\n" for l in s.split("\n")]
    pieces = [re.split(pattern, l) for l in lines]
    flatten = [i for sl in pieces for i in sl]
    def replace_ref(t):
        if re.match(pattern, t):
            return Ref(t[4:-1])
        else:
            return t
    return [replace_ref(x) for x in flatten]

def make_content(s, fixrefs=True):
    return Join('', split_content(s, fixrefs))

def make_user_data(s):
    return Base64(make_content(s))

def merge(*dicts):
    result = {}
    for dictionary in dicts:
        result.update(dictionary)
    return result
