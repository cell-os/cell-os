import sys
import os
import string

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

import troposphere.iam as iam
import troposphere.ec2 as ec2
import troposphere.elasticloadbalancing as elb
import troposphere.cloudformation as cfn
from tropopause import *

from troposphere import Not, Ref, Equals, If, Tags
from troposphere import Base64, Select, FindInMap, GetAtt, GetAZs, Join, Output
from troposphere import Parameter, Ref, Tags, Template
from troposphere.s3 import BucketPolicy
from troposphere.ec2 import VPCEndpoint

t = Template()

t.add_version("2010-09-09")

t.add_description("""\
cell-os-base - https://git.corp.adobe.com/metal-cell/cell-os""")

CellName = t.add_parameter(Parameter(
    "CellName",
    Default="cell-1",
    Type="String",
    Description="The name of this cell (e.g. cell-1). This will get prefixed with account id and region to get the full cell id.",
))

CellOsVersionBundle = t.add_parameter(Parameter(
    "CellOsVersionBundle",
    Default="cell-os-base-1.2-SNAPSHOT",
    Type="String",
    Description="cell-os bundle version",
))

SaasBaseDeploymentVersion = t.add_parameter(Parameter(
    "SaasBaseDeploymentVersion",
    Default="1.27",
    Type="String",
    Description="saasbase-deployment version",
))

KeyName = t.add_parameter(Parameter(
    "KeyName",
    Type="AWS::EC2::KeyPair::KeyName",
    Description="Existing EC2 KeyPair to be associated with all cluster instances for SSH access. The default user is 'centos'",
))

NucleusSize = t.add_parameter(Parameter(
    "NucleusSize",
    Default="3",
    Type="Number",
    Description="Number of nodes in the cell nucleus",
))

accepted_instance_types = [
    "t2.micro", "t2.small", "t2.medium", "t2.large",
    "m1.small", "m1.medium", "m1.large", "m1.xlarge",
    "m2.xlarge", "m2.2xlarge", "m2.4xlarge",
    "m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge",
    "m4.large", "m4.xlarge", "m4.2xlarge", "m4.4xlarge", "m4.10xlarge",
    "c4.large", "c4.xlarge", "c4.2xlarge", "c4.4xlarge", "c4.8xlarge",
    "c3.large", "c3.xlarge", "c3.2xlarge", "c3.4xlarge", "c3.8xlarge",
    "r3.large", "r3.xlarge", "r3.2xlarge", "r3.4xlarge", "r3.8xlarge",
    "g2.2xlarge", "g2.8xlarge",
    "i2.xlarge", "i2.2xlarge", "i2.4xlarge", "i2.8xlarge",
    "d2.xlarge", "d2.2xlarge", "d2.4xlarge", "d2.8xlarge",
    "hs1.8xlarge",
    "hi1.4xlarge",
    "cc2.8xlarge"
]

NucleusInstanceType = t.add_parameter(Parameter(
    "NucleusInstanceType",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="Nucleus EC2 instance type",
    AllowedValues=accepted_instance_types,
))

StatelessBodySize = t.add_parameter(Parameter(
    "StatelessBodySize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell stateless body",
))

StatelessBodyInstanceType = t.add_parameter(Parameter(
    "StatelessBodyInstanceType",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="StatelessBody EC2 instance type",
    AllowedValues=accepted_instance_types,
))

StatefulBodySize = t.add_parameter(Parameter(
    "StatefulBodySize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell stateful body (local disk access)",
))

StatefulBodyInstanceType = t.add_parameter(Parameter(
    "StatefulBodyInstanceType",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="StatefulBody EC2 instance type",
    AllowedValues=accepted_instance_types,
))

MembraneSize = t.add_parameter(Parameter(
    "MembraneSize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell membrane, which is publicly exposed",
))

MembraneInstanceType = t.add_parameter(Parameter(
    "MembraneInstanceType",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="Membrane EC2 instance type",
    AllowedValues=accepted_instance_types,
))

BucketName = t.add_parameter(Parameter(
    "BucketName",
    Type="String",
    Description="Cell's S3 bucket name. This needs to be an existing bucket, so you have to create it first.",
))

SaasBaseAccessKeyId = t.add_parameter(Parameter(
    "SaasBaseAccessKeyId",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Access Key ID (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

SaasBaseSecretAccessKey = t.add_parameter(Parameter(
    "SaasBaseSecretAccessKey",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Secret Access Key (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

BodyStackTemplate = t.add_parameter(Parameter(
    "BodyStackTemplate",
    Default="elastic-cell-scaling-group.json",
    Type="String",
    Description="",
))

t.add_mapping("RegionMap", {
    'ap-northeast-1': {'AMI': 'ami-24f47024'},
    'ap-southeast-1': {'AMI': 'ami-3e9e906c'},
    'ap-southeast-2': {'AMI': 'ami-f54d0fcf'},
    'eu-central-1': {'AMI': 'ami-649d9a79'},
    'eu-west-1': {'AMI': 'ami-e2580795'},
    'sa-east-1': {'AMI': 'ami-476ae25a'},
    'us-east-1': {'AMI': 'ami-11b7017a'},
    'us-west-1': {'AMI': 'ami-37a45d73'},
    'us-west-2': {'AMI': 'ami-bd5b4f8d'}
})

t.add_condition(
    "RegionIsUsEast1", Equals(Ref("AWS::Region"), "us-east-1")
)

t.add_output(Output(
    "MesosElbOutput",
    Description="Address of the Mesos LB",
    Value=Join('', ['http://', GetAtt("MesosElb", 'DNSName')]),
))

t.add_output(Output(
    "ZookeeperElbOutput",
    Description="Address of the Exhibitor LB",
    Value=Join('', ['http://', GetAtt("ZookeeperElb", 'DNSName')]),
))

t.add_output(Output(
    "MembraneElbOutput",
    Description="Address of the Membrane LB",
    Value=Join('', ['http://', GetAtt("MembraneElb", 'DNSName')]),
))

t.add_output(Output(
    "MarathonElbOutput",
    Description="Address of the Mesos LB",
    Value=Join('', ['http://', GetAtt("MarathonElb", 'DNSName')]),
))

VPC = t.add_resource(ec2.VPC(
    "VPC",
    EnableDnsSupport=True,
    CidrBlock="10.0.0.0/16",
    EnableDnsHostnames=True,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

# region domain is ec2.internal in us-east-1, REGION.compute.internal for
# others, according to
# http://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/VPC_DHCP_Options.html
DHCP = t.add_resource(ec2.DHCPOptions(
    'DHCP',
    DomainName=If(
        "RegionIsUsEast1",
        "ec2.internal",
        Join("", [Ref("AWS::Region"), ".compute.internal"])
    ),
    DomainNameServers=['AmazonProvidedDNS', '169.254.169.253']
))

VPCDHCPOptionsAssociation = t.add_resource(ec2.VPCDHCPOptionsAssociation(
    'DHCPAssoc',
    DhcpOptionsId=Ref("DHCP"),
    VpcId=Ref("VPC")
))

Subnet = t.add_resource(ec2.Subnet(
    "Subnet",
    VpcId=Ref("VPC"),
    CidrBlock="10.0.0.0/24",
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

InternetGateway = t.add_resource(ec2.InternetGateway(
    "InternetGateway",
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

AttachGateway = t.add_resource(ec2.VPCGatewayAttachment(
    "AttachGateway",
    VpcId=Ref(VPC),
    InternetGatewayId=Ref("InternetGateway")
))

RouteTable = t.add_resource(ec2.RouteTable(
    "RouteTable",
    VpcId=Ref(VPC),
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

Route = t.add_resource(ec2.Route(
    "Route",
    GatewayId=Ref(InternetGateway),
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref("RouteTable"),
    DependsOn="AttachGateway",
))

SubnetRouteTableAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
    "SubnetRouteTableAssociation",
    SubnetId=Ref(Subnet),
    RouteTableId=Ref("RouteTable"),
))

NucleusS3Policy = t.add_resource(iam.PolicyType(
    'NucleusS3Policy',
    PolicyName='NucleusS3Policy',
    PolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Resource=[
                    Join("", ["arn:aws:s3:::", Ref(BucketName)]),
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/cell-os--", Ref("CellName"), "/*"]),
                    #FIXME: this is an Exhibitor configuration issue, it creates the backups in /cell-os--cellname_nucleus_exhibitor
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/cell-os--", Ref("CellName"), "_nucleus_exhibitor"]),
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/cell-os--", Ref("CellName"), "_nucleus_exhibitor/*"]),
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/*"]),
                ],
                Action=[
                    awacs.aws.Action("s3", "AbortMultipartUpload"),
                    awacs.aws.Action("s3", "DeleteObject"),
                    awacs.aws.Action("s3", "GetBucketAcl"),
                    awacs.aws.Action("s3", "GetBucketPolicy"),
                    awacs.aws.Action("s3", "GetObject"),
                    awacs.aws.Action("s3", "GetObjectAcl"),
                    awacs.aws.Action("s3", "GetObjectVersion"),
                    awacs.aws.Action("s3", "GetObjectVersionAcl"),
                    awacs.aws.Action("s3", "ListBucket"),
                    awacs.aws.Action("s3", "ListBucketMultipartUploads"),
                    awacs.aws.Action("s3", "ListBucketVersions"),
                    awacs.aws.Action("s3", "ListMultipartUploadParts"),
                    awacs.aws.Action("s3", "PutObject"),
                    awacs.aws.Action("s3", "PutObjectAcl"),
                    awacs.aws.Action("s3", "PutObjectVersionAcl")
                ]
            )
        ]
    ),
    Roles=[
        Ref("NucleusRole"),
    ]
))

def s3_ro_policy(name, roles, paths):
    resources = [Join("", ["arn:aws:s3:::", Ref("BucketName")])]
    for path in paths:
        join_args = ["arn:aws:s3:::", Ref("BucketName"), "/"]
        join_args.extend(path)
        resources.append(
            Join("", join_args)
        )
    return iam.PolicyType(
        name,
        PolicyName=name,
        PolicyDocument=awacs.aws.Policy(
            Statement=[
                awacs.aws.Statement(
                    Effect=awacs.aws.Allow,
                    Resource=resources,
                    Action=[
                        awacs.aws.Action("s3", "GetBucketAcl"),
                        awacs.aws.Action("s3", "GetBucketPolicy"),
                        awacs.aws.Action("s3", "GetObject"),
                        awacs.aws.Action("s3", "GetObjectAcl"),
                        awacs.aws.Action("s3", "GetObjectVersion"),
                        awacs.aws.Action("s3", "GetObjectVersionAcl"),
                        awacs.aws.Action("s3", "ListBucket"),
                        awacs.aws.Action("s3", "ListBucketMultipartUploads"),
                        awacs.aws.Action("s3", "ListBucketVersions"),
                        awacs.aws.Action("s3", "ListMultipartUploadParts"),
                    ]
                )
            ]
        ),
        Roles=[Ref(role) for role in roles]
    )

MembraneReadOnlyPolicy = s3_ro_policy(
    "MembraneReadOnlyS3Policy",
    ["MembraneRole"],
    [["cell-os--", Ref("CellName"), "/membrane/*"]]
)
t.add_resource(MembraneReadOnlyPolicy)
StatelessBodyReadOnlyPolicy = s3_ro_policy(
    "StatelessBodyReadOnlyS3Policy",
    ["StatelessBodyRole"],
    [["cell-os--", Ref("CellName"), "/stateless-body/*"]]
)
t.add_resource(StatelessBodyReadOnlyPolicy)
StatefulBodyReadOnlyPolicy = s3_ro_policy(
    "StatefulBodyReadOnlyS3Policy",
    ["StatefulBodyRole"],
    [["cell-os--", Ref("CellName"), "/stateful-body/*"]]
)
t.add_resource(StatefulBodyReadOnlyPolicy)
SharedReadOnlyPolicy = s3_ro_policy(
    "SharedReadOnlyS3Policy",
    ["StatelessBodyRole", "StatefulBodyRole", "MembraneRole"],
    [["cell-os--", Ref("CellName"), "/shared/*"]]
)
t.add_resource(SharedReadOnlyPolicy)

# In order for the HTTP Bucket Policy to work a VPCEndpoint needs to be created.
# A VPC endpoint enables you to create a private connection between your VPC and another AWS service
# without requiring access over the Internet, through a NAT device, a VPN connection, or AWS Direct Connect.
VpcEndpointS3 = VPCEndpoint(
    "VpcEndpointS3",
    RouteTableIds=[Ref("RouteTable")],
    ServiceName=Join("", ["com.amazonaws.", Ref("AWS::Region"), ".s3"]),
    VpcId=Ref(VPC),
)
t.add_resource(VpcEndpointS3)

SharedReadOnlyHTTPPolicy = BucketPolicy(
    "BucketHTTPReadonlyS3Policy",
    Bucket=Ref(BucketName),
    PolicyDocument={
        "Version": "2008-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/cell-os--", Ref("CellName"), "/shared/http/*"]),
                ],
                "Condition": {
                    "StringEquals": {
                        "aws:sourceVpce": Ref(VpcEndpointS3)
                    }
                }
            }
        ]
    }
)
t.add_resource(SharedReadOnlyHTTPPolicy)

NucleusEc2Policy = t.add_resource(iam.PolicyType(
    'NucleusEc2Policy',
    PolicyName='NucleusEc2Policy',
    PolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Resource=["*"],
                Action=[
                    awacs.aws.Action("ec2", "Describe*"),
                ]
            )
        ]
    ),
    Roles=[
        Ref("NucleusRole"),
        Ref("StatefulBodyRole")
    ]
))

NucleusCfnPolicy = t.add_resource(iam.PolicyType(
    'NucleusCfnPolicy',
    PolicyName='NucleusCfnPolicy',
    PolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Resource=["*"],
                Action=[
                    awacs.aws.Action("autoscaling", "Describe*"),
                    awacs.aws.Action("cloudformation", "Describe*"),
                    awacs.aws.Action("cloudformation", "GetStackPolicy"),
                    awacs.aws.Action("cloudformation", "GetTemplate*"),
                    awacs.aws.Action("cloudformation", "ListStacks"),
                    awacs.aws.Action("cloudformation", "ListStackResources"),
                ]
            )
        ]
    ),
    Roles=[
        Ref("NucleusRole"),
        Ref("StatefulBodyRole")
    ]
))

NucleusRole = t.add_resource(iam.Role(
    "NucleusRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

NucleusInstanceProfile = t.add_resource(iam.InstanceProfile(
    "NucleusInstanceProfile",
    Path="/",
    Roles=[Ref(NucleusRole)],
))

MembraneRole = t.add_resource(iam.Role(
    "MembraneRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

MembraneInstanceProfile = t.add_resource(iam.InstanceProfile(
    "MembraneInstanceProfile",
    Path="/",
    Roles=[Ref(MembraneRole)],
))

StatelessBodyRole = t.add_resource(iam.Role(
    "StatelessBodyRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

StatelessBodyInstanceProfile = t.add_resource(iam.InstanceProfile(
    "StatelessBodyInstanceProfile",
    Path="/",
    Roles=[Ref(StatelessBodyRole)],
))

StatefulBodyRole = t.add_resource(iam.Role(
    "StatefulBodyRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

StatefulBodyInstanceProfile = t.add_resource(iam.InstanceProfile(
    "StatefulBodyInstanceProfile",
    Path="/",
    Roles=[Ref(StatefulBodyRole)],
))

BodySecurityGroup = t.add_resource(security_group(
    'BodySecurityGroup',
    """
ingress LbSecurityGroup tcp 80:80
ingress LbSecurityGroup tcp 5050:5050
ingress LbSecurityGroup tcp 8080:8080
ingress LbSecurityGroup tcp 8181:8181
    """,
    VPC,
    description="All nodes in body. Grants access to LbSecurityGroup"
))

NucleusSecurityGroup = t.add_resource(security_group(
    'NucleusSecurityGroup',
    """
ingress LbSecurityGroup tcp 8181:8181
ingress BodySecurityGroup tcp 2181:2181
ingress BodySecurityGroup tcp 2888:2888
ingress BodySecurityGroup tcp 3888:3888
ingress BodySecurityGroup tcp 8181:8181
ingress BodySecurityGroup tcp 9000:9001
ingress BodySecurityGroup tcp 50000:50100
    """,
    VPC,
    description="All nucleus nodes. Grants access to Exhibitor, ZK ports from LB and Body SG, respectively"
))

ExternalWhitelistSecurityGroup = t.add_resource(security_group(
    'ExternalWhitelistSecurityGroup',
    """
# Bucharest
ingress 127.127.140.131/32  tcp  0:65535
# Dublin
ingress 127.127.215.11/32  tcp  0:65535
ingress 127.127.215.13/32  tcp  0:65535
# Hamburg
ingress 127.127.139.131/32  tcp  0:65535
ingress 127.127.139.132/32  tcp  0:65535
ingress 127.127.58.150/32  tcp  0:65535
ingress 127.127.58.180/32  tcp  0:65535
# London
ingress 127.127.65.2/32  tcp  0:65535
# Paris
ingress 127.127.98.227/32  tcp  0:65535
# Beijing
# Singapore
# Seoul
ingress 127.127.24.4/32  tcp  0:65535
# Sydney
ingress 127.127.121.82/32  tcp  0:65535
# Tokyo
ingress 127.127.93.230/32  tcp  0:65535
ingress 127.127.93.231/32  tcp  0:65535
# Bangalore
ingress 127.127.216.100/32  tcp  0:65535
# Noida
ingress 127.127.112.97/32  tcp  0:65535
ingress 127.127.112.98/32  tcp  0:65535
# Basel
ingress 127.127.117.11/32  tcp  0:65535
# Lehi
ingress 127.127.9.200/32  tcp  0:65535
ingress 127.127.9.201/32  tcp  0:65535
# Los Angeles
ingress 127.127.170.7/32  tcp  0:65535
ingress 127.127.170.15/32  tcp  0:65535
ingress 127.127.170.24/32  tcp  0:65535
ingress 127.127.170.104/32  tcp  0:65535
ingress 127.127.170.204/32  tcp  0:65535
# New Jersey
ingress 127.127.3.7/32  tcp  0:65535
ingress 127.127.3.136/32  tcp  0:65535
# San Jose
# San Francisco
ingress 127.127.10.200/32  tcp  0:65535
ingress 127.127.10.201/32  tcp  0:65535
ingress 127.127.10.202/32  tcp  0:65535
ingress 127.127.10.203/32  tcp  0:65535
ingress 127.127.10.204/32  tcp  0:65535
ingress 127.127.10.205/32  tcp  0:65535
ingress 127.127.10.206/32  tcp  0:65535
ingress 127.127.10.207/32  tcp  0:65535
ingress 127.127.10.208/32  tcp  0:65535
ingress 127.127.10.209/32  tcp  0:65535
    """,
    VPC,
    description="All nodes are part of it. Grants access to some Adobe CIDRs. Email to metal-cell@adobe.com"
))

LbSecurityGroup = t.add_resource(ec2.SecurityGroup(
    "LbSecurityGroup",
    GroupDescription="Added to ELBs that require access to instances.",
    VpcId=Ref(VPC)
))

PublicSecurityGroup = t.add_resource(security_group(
    'PublicSecurityGroup',
    """
ingress 0.0.0.0/0 tcp 80:80
ingress 0.0.0.0/0 tcp 443:443
    """,
    VPC,
    description="Public access for all nodes in this group. Tread carefully."
))

# format: name  type  source  dest tcp  port-range
vpc_security_group_rules = vpc_security_rules("""\
BodyToLbIngress ingress BodySecurityGroup LbSecurityGroup tcp 0:65535
BodyToBodyIngress ingress BodySecurityGroup BodySecurityGroup -1 0:65535
NucleusToLbIngress ingress NucleusSecurityGroup LbSecurityGroup tcp 80:80
NucleusToNucleusIngress ingress NucleusSecurityGroup NucleusSecurityGroup -1 0:65535
""")

for rule in vpc_security_group_rules:
    t.add_resource(rule)

def create_load_balancer(t, name, instance_port, target,
        security_groups=[Ref("LbSecurityGroup")], internal=True):
    return t.add_resource(elb.LoadBalancer(
        name + "Elb",
        DependsOn="AttachGateway",
        LoadBalancerName=Join("", [Ref("CellName"), "-" + name.lower()]),
        CrossZone="true",
        Scheme="internal" if internal else "internet-facing",
        SecurityGroups=security_groups,
        Subnets=[Ref(Subnet)],
        Listeners=[{
            "InstancePort": str(instance_port),
            "LoadBalancerPort": "80",
            "Protocol": "HTTP"
        }],
        HealthCheck=elb.HealthCheck(
            HealthyThreshold="3",
            Interval="30",
            Target="HTTP:%d%s" % (instance_port, target),
            Timeout="5",
            UnhealthyThreshold="5",
        ),
        Tags=Tags(
            cell=Ref(CellName),
        ),
    ))


MarathonElb = create_load_balancer(t,
    "Marathon",
    8080,
    "/status"
)

ZookeeperElb = create_load_balancer(t,
    "Zookeeper",
    8181,
    "/exhibitor/v1/cluster/state"
)

MesosElb = create_load_balancer(t,
    "Mesos",
    5050,
    "/health"
)

MembraneElb = create_load_balancer(t,
    "Membrane",
    80,
    "/health-check",
    [Ref("PublicSecurityGroup")],
    False
)

WaitHandle = t.add_resource(cfn.WaitConditionHandle("WaitHandle",))

def create_cellos_substack(t, name=None, role=None, cell_modules=None, tags=[], security_groups=[], load_balancers=[], instance_profile=None, instance_type=None):
    params = {
        "Role": role,
        "Tags": tags,
        "CellModules": cell_modules,
        "SecurityGroups": Join(",", security_groups),
        "LoadBalancerNames": Join(",", load_balancers),
        "ZookeeperElb": GetAtt("ZookeeperElb", "DNSName"),
        "MarathonElb": GetAtt("MarathonElb", "DNSName"),
        "MesosElb": GetAtt("MesosElb", "DNSName"),
        "MembraneElb": GetAtt("MembraneElb", "DNSName"),
        "AssociatePublicIpAddress": "true",
        "GroupSize": Ref(name + "Size"),
        "ImageId": FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
        "CellName": Ref("CellName"),
        "BucketName": Ref("BucketName"),
        "CellOsVersionBundle": Ref("CellOsVersionBundle"),
        "InstanceType": instance_type,
        "Subnet": Ref("Subnet"),
        "KeyName": Ref("KeyName"),
        "SaasBaseDeploymentVersion": Ref("SaasBaseDeploymentVersion"),
        "SaasBaseSecretAccessKey": Ref("SaasBaseSecretAccessKey"),
        "SaasBaseAccessKeyId": Ref("SaasBaseAccessKeyId"),
        "ParentStackName": Ref("AWS::StackName"),
        "WaitHandle": Ref("WaitHandle"),
    }
    if instance_profile != None:
        params["IamInstanceProfile"] = Ref(instance_profile)

    substack_template_url = Join("", ["https://s3.amazonaws.com/", Ref("BucketName"), "/", "cell-os--", Ref("CellName"), "/", Ref("BodyStackTemplate")])
    # check if the template url is overridden (e.g. with a release one)
    if len(sys.argv) > 1 and len(sys.argv[1]) > 7 :
        substack_template_url = sys.argv[1]

    t.add_resource(cfn.Stack(
        name + "Stack",
        TemplateURL=substack_template_url,
        DependsOn="AttachGateway",
        TimeoutInMinutes="10",
        Parameters=params
    ))

create_cellos_substack(
    t,
    name="Nucleus",
    role="nucleus",
    cell_modules="00-docker,00-java,01-exhibitor,10-hdfs-raw,99-cell",
    tags="nucleus",
    instance_profile="NucleusInstanceProfile",
    security_groups=[
        Ref(NucleusSecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[Ref("ZookeeperElb")],
    instance_type=Ref("NucleusInstanceType")
)

create_cellos_substack(
    t,
    name="Membrane",
    role="membrane",
    cell_modules="00-docker,02-mesos,99-cell",
    tags="membrane,slave,body",
    instance_profile="MembraneInstanceProfile",
    security_groups=[
        Ref(PublicSecurityGroup),
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MembraneElb")
    ],
    instance_type=Ref("MembraneInstanceType")
)

create_cellos_substack(
    t,
    name="StatelessBody",
    role="stateless-body",
    cell_modules="00-docker,00-java,01-exhibitor,02-mesos,10-marathon,99-cell",
    tags="slave,body,stateless,stateless-body",
    instance_profile="StatelessBodyInstanceProfile",
    security_groups=[
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MesosElb"),
        Ref("MarathonElb")
    ],
    instance_type=Ref("StatelessBodyInstanceType")
)

create_cellos_substack(
    t,
    name="StatefulBody",
    role="stateful-body",
    cell_modules="00-docker,00-java,02-mesos,10-hdfs-raw,99-cell",
    tags="slave,body,stateful,stateful-body",
    instance_profile="StatefulBodyInstanceProfile",
    security_groups=[
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MesosElb"),
        Ref("MarathonElb")
    ],
    instance_type=Ref("StatefulBodyInstanceType")
)

print(t.to_json(indent=2))
