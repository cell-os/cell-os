from __future__ import unicode_literals
from optparse import OptionParser

import awacs
import awacs.autoscaling
import awacs.aws
import awacs.cloudformation
import awacs.cloudfront
import awacs.cloudwatch
import awacs.dynamodb
import awacs.ec2
import awacs.elasticloadbalancing
import awacs.iam
import awacs.s3
import awacs.sqs
import awacs.sts
import pystache
import troposphere.cloudformation as cfn
import troposphere.elasticloadbalancing as elb
import troposphere.iam as iam
import troposphere.route53 as route53
import yaml
from tropopause import *
from troposphere import Equals, If, Condition
from troposphere import FindInMap, GetAtt, Join, Output
from troposphere import Parameter, Ref, Tags, Template
from troposphere.ec2 import VPCEndpoint
from troposphere.s3 import BucketPolicy
import ipaddress

pkg_dir = os.path.dirname(os.path.abspath(__file__))

parser = OptionParser()
parser.add_option('--cidr', dest='cidr', help='VPC CIDR to use', default="10.0.0.0/16")
parser.add_option('--template-url', dest='template_url', help='CFN template URL')
parser.add_option('--net-whitelist', dest='net_whitelist',
                   help='Location to network whitelist config file')
(options, args) = parser.parse_args()
if not options.net_whitelist:
    parser.error('Missing location to network whitelist config file')
net_whitelist = json.loads(open(options.net_whitelist, "rb+").read())

modules = {}
with open(os.path.join(pkg_dir, "../config/cell.yaml"), 'r') as stream:
    cell = yaml.load(stream)
    for role in ['nucleus', 'membrane', 'stateless-body', 'stateful-body',
                 'bastion']:
        modules[role] = ",".join(cell[role]['modules'])

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

Repository = t.add_parameter(Parameter(
    "Repository",
    Default="s3://saasbase-repo",
    Type="String",
    Description="Location of provisioning related artefacts",
))

CellOsVersionBundle = t.add_parameter(Parameter(
    "CellOsVersionBundle",
    Default="cell-os-base-1.2.1-SNAPSHOT",
    Type="String",
    Description="cell-os bundle version",
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

BastionSize = t.add_parameter(Parameter(
    "BastionSize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell bastion",
))

EipAllocation = t.add_parameter(Parameter(
    "EipAllocation",
    Default="",
    Type="String",
    Description="The AllocationId of the VPC Elastic IP (eg. eipalloc-5723d3e)."
                " If empty, we'll just allocate a new EIP.",
))

# TODO: decide whether we want to make these parameters
cell_domain_prefix = "gw."
cell_domain_suffix = ".metal-cell.adobe.io"
def cell_domain():
    return [cell_domain_prefix, Ref("CellName"), cell_domain_suffix]

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

BastionInstanceType = t.add_parameter(Parameter(
    "BastionInstanceType",
    Default="t2.micro",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="Bastion EC2 instance type",
    AllowedValues=accepted_instance_types,
))

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
    'eu-west-1': { 'AMI': 'ami-4824b23b'},
    'ap-southeast-1': { 'AMI': 'ami-e4c91887'},
    'ap-southeast-2': { 'AMI': 'ami-848da2e7'},
    'eu-central-1': { 'AMI': 'ami-11be517e'},
    'ap-northeast-2': { 'AMI': 'ami-11b8737f'},
    'ap-northeast-1': { 'AMI': 'ami-495ebd28'},
    'us-east-1': { 'AMI': 'ami-646e9909'},
    'sa-east-1': { 'AMI': 'ami-f4cd4698'},
    'us-west-1': { 'AMI': 'ami-3f0a715f'},
    'us-west-2': { 'AMI': 'ami-f5c73995'}
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
    "GatewayElbOutput",
    Description="Address of the Gateway LB",
    Value=Join('', ['http://', GetAtt("GatewayElb", 'DNSName')]),
))

t.add_output(Output(
    "InternalGatewayElbOutput",
    Description="Address of the Internal Gateway LB",
    Value=Join('', ['http://', GetAtt("IGatewayElb", 'DNSName')]),
))

t.add_output(Output(
    "MarathonElbOutput",
    Description="Address of the Mesos LB",
    Value=Join('', ['http://', GetAtt("MarathonElb", 'DNSName')]),
))

cidr_block = unicode(options.cidr)
net_calc = ipaddress.IPv4Network(cidr_block)
subnets = list(net_calc.subnets())
public_subnet_cidr_block = str(subnets[0])
private_subnet_cidr_block = str(subnets[1])

VPC = t.add_resource(ec2.VPC(
    "VPC",
    EnableDnsSupport=True,
    CidrBlock=options.cidr,
    EnableDnsHostnames=True,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

HostedZone = t.add_resource(route53.HostedZone(
    "HostedZone",
    HostedZoneConfig=route53.HostedZoneConfiguration(
        Comment="Cell hosted zone"
    ),
    Name=Join("", cell_domain()),
    VPCs=[
        route53.HostedZoneVPCs(
            VPCId=Ref(VPC),
            VPCRegion=Ref("AWS::Region")
        )
    ]
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
    DomainNameServers=['AmazonProvidedDNS']
))

VPCDHCPOptionsAssociation = t.add_resource(ec2.VPCDHCPOptionsAssociation(
    'DHCPAssoc',
    DhcpOptionsId=Ref("DHCP"),
    VpcId=Ref(VPC)
))

public_subnet = t.add_resource(ec2.Subnet(
    "PublicSubnet",
    VpcId=Ref(VPC),
    CidrBlock=public_subnet_cidr_block,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))


# Use the provided EIP allocation if defined
t.add_condition("no_eip_allocation", Equals(Ref(EipAllocation), ""))
# Note that we may end up having an unused EIP in that case.
# TODO only reserve EIP if no_eip_allocation
nat_eip = t.add_resource(ec2.EIP(
    "NatEip",
    Domain="vpc"
))

nat_gw = t.add_resource(ec2.NatGateway(
    "NatGateway",
    # Don't replace with Ref(nat_eip) as it will throw:
    #   "Elastic IP address could not be associated with this NAT gateway"
    # See https://forums.aws.amazon.com/thread.jspa?messageID=710312
    AllocationId=If("no_eip_allocation", GetAtt(nat_eip, 'AllocationId'),
                    Ref(EipAllocation), ),
    SubnetId=Ref(public_subnet),
))

public_route_table = t.add_resource(ec2.RouteTable(
    "PublicRouteTable",
    VpcId=Ref(VPC),
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

default_public_route = t.add_resource(ec2.Route(
    "Route",
    GatewayId=Ref(InternetGateway),
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref(public_route_table),
    DependsOn="AttachGateway",
))

public_subnet_route_table_association = t.add_resource(ec2.SubnetRouteTableAssociation(
    "SubnetRouteTableAssociation",
    SubnetId=Ref(public_subnet),
    RouteTableId=Ref(public_route_table),
))


private_subnet = t.add_resource(ec2.Subnet(
    "PrivateSubnet",
    VpcId=Ref(VPC),
    # Ensure our public and private subnets are collocated in the same AZ
    AvailabilityZone=GetAtt(public_subnet, 'AvailabilityZone'),
    CidrBlock=private_subnet_cidr_block,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

private_route_table = t.add_resource(ec2.RouteTable(
    "RouteTable",
    VpcId=Ref(VPC),
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

default_private_route = t.add_resource(ec2.Route(
    "DefaultPrivateRoute",
    NatGatewayId=Ref(nat_gw),
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref(private_route_table),

))

private_subnet_route_table_association = t.add_resource(ec2.SubnetRouteTableAssociation(
    "PrivateSubnetRouteTableAssociation",
    SubnetId=Ref(private_subnet),
    RouteTableId=Ref(private_route_table),
))

def s3_policy(name, roles, paths, mode="ro"):
    resources = []
    for path in paths:
        join_args = ["arn:aws:s3:::", Ref("BucketName")]
        join_args.extend(path)
        resources.append(
            Join("", join_args)
        )
    actions = [
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
    if mode == "rw":
        actions.extend([
            awacs.aws.Action("s3", "AbortMultipartUpload"),
            awacs.aws.Action("s3", "DeleteObject"),
            awacs.aws.Action("s3", "PutObject"),
            awacs.aws.Action("s3", "PutObjectAcl"),
            awacs.aws.Action("s3", "PutObjectVersionAcl")
        ])

    return iam.PolicyType(
        name,
        PolicyName=name,
        PolicyDocument=awacs.aws.Policy(
            Statement=[
                awacs.aws.Statement(
                    Effect=awacs.aws.Allow,
                    Resource=resources,
                    Action=actions
                )
            ]
        ),
        Roles=[Ref(role) for role in roles]
    )

NucleusS3Policy = s3_policy(
    "NucleusS3Policy",
    ["NucleusRole"],
    [
        [],
        ["/cell-os--", Ref("CellName"), "/*"],
        ["/cell-os--", Ref("CellName"), "_nucleus_exhibitor"],
        ["/cell-os--", Ref("CellName"), "_nucleus_exhibitor/*"],
        ["/*"]
    ],
    mode="rw"
)
t.add_resource(NucleusS3Policy)

MembraneReadOnlyPolicy = s3_policy(
    "MembraneReadOnlyS3Policy",
    ["MembraneRole"],
    [[], ["/cell-os--", Ref("CellName"), "/membrane/*"]],
    mode="ro"
)
t.add_resource(MembraneReadOnlyPolicy)

StatelessBodyReadOnlyPolicy = s3_policy(
    "StatelessBodyReadOnlyS3Policy",
    ["StatelessBodyRole"],
    [[], ["/cell-os--", Ref("CellName"), "/stateless-body/*"]],
    mode="ro"
)
t.add_resource(StatelessBodyReadOnlyPolicy)

StatefulBodyReadOnlyPolicy = s3_policy(
    "StatefulBodyReadOnlyS3Policy",
    ["StatefulBodyRole"],
    [[], ["/cell-os--", Ref("CellName"), "/stateful-body/*"]],
    mode="ro"
)
t.add_resource(StatefulBodyReadOnlyPolicy)

SharedReadOnlyPolicy = s3_policy(
    "SharedReadOnlyS3Policy",
    ["StatelessBodyRole", "StatefulBodyRole", "MembraneRole"],
    [[], ["/cell-os--", Ref("CellName"), "/shared/*"]],
    mode="ro"
)
t.add_resource(SharedReadOnlyPolicy)

SharedStatusRWPolicy = s3_policy(
    "SharedStatusRWPolicy",
    ["StatelessBodyRole", "StatefulBodyRole", "MembraneRole", "NucleusRole"],
    [["/cell-os--", Ref("CellName"), "/shared/status/*"]],
    mode="rw"
)
t.add_resource(SharedStatusRWPolicy)

# In order to access an S3 bucket from HTTP we need a VpcEndpoint
# A VPC endpoint enables you to create a private connection between your VPC and another AWS service
# without requiring access over the Internet, through a NAT device, a VPN connection, or AWS Direct Connect.
# http://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/vpc-endpoints.html
VpcEndpointS3 = VPCEndpoint(
    "VpcEndpointS3",
    RouteTableIds=[Ref("RouteTable"), Ref("PublicRouteTable")],
    ServiceName=Join("", ["com.amazonaws.", Ref("AWS::Region"), ".s3"]),
    VpcId=Ref(VPC),
)
t.add_resource(VpcEndpointS3)

egress_nets = ["{}/{}".format(entry['addr'], entry['mask'])
                for entry in net_whitelist]

SharedBucketPolicy = BucketPolicy(
    "SharedBucketPolicy",
    Bucket=Ref(BucketName),
    PolicyDocument={
        "Version": "2008-10-17",
        "Statement": [
            # Read only HTTP access for S3 /shared/http
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
            },
            # public list needed by the status page
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": [
                    "s3:ListBucket"
                ],
                "Resource": [
                    Join("", ["arn:aws:s3:::", Ref(BucketName)]),
                ],
                "Condition": {
                    "StringLike": {
                        # S3 lists the entire bucket recursively, so we need to filter
                        "s3:prefix": [Join("", ["cell-os--", Ref("CellName"), "/shared/status/*"])],
                    },
                    "IpAddress": {
                        "aws:SourceIp": egress_nets
                    }
                }
            },
            # public read needed by the status page
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": [
                    "s3:GetObject",
                ],
                "Resource": [
                    Join("", ["arn:aws:s3:::", Ref(BucketName), "/cell-os--", Ref("CellName"), "/shared/status/*"]),
                ],
                "Condition": {
                    "IpAddress": {
                        "aws:SourceIp": egress_nets
                    }
                }
            }
        ]
    }
)
t.add_resource(SharedBucketPolicy)

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
        Ref("StatefulBodyRole"),
        Ref("StatelessBodyRole"),
        Ref("MembraneRole")
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

CloudWatchLogsPolicy = t.add_resource(iam.PolicyType(
    'CloudWatchLogsPolicy',
    PolicyName='CloudWatchLogsPolicy',
    PolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Resource=["arn:aws:logs:*:*:*"],
                Action=[
                    awacs.aws.Action("logs", "CreateLogGroup"),
                    awacs.aws.Action("logs", "CreateLogStream"),
                    awacs.aws.Action("logs", "PutLogEvents"),
                    awacs.aws.Action("logs", "DescribeLogStreams")
                ]
            )
        ]
    ),
    Roles=[
        Ref("NucleusRole"),
        Ref("StatefulBodyRole"),
        Ref("StatelessBodyRole"),
        Ref("MembraneRole")
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

BastionSecurityGroup = t.add_resource(security_group(
    'BastionSecurityGroup',
    "",
    VPC,
    description="Bastion nodes have access to all other nodes over SSH"
))


ExternalWhitelistSecurityGroup = t.add_resource(security_group(
    'ExternalWhitelistSecurityGroup',
    pystache.render("""
{{#entries}}
ingress {{addr}}/{{mask}} tcp 0:65535
{{/entries}}
""", {'entries': net_whitelist }),
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
BastionToNucleus ingress BastionSecurityGroup NucleusSecurityGroup tcp 22:22
BastionToBody ingress BastionSecurityGroup BodySecurityGroup tcp 22:22
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
        # Note that if multiple subnets defined, they must be in separate AZs.
        Subnets=[Ref(private_subnet) if internal else Ref(public_subnet)],
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

GatewayElb = create_load_balancer(t,
    "Gateway",
    80,
    "/health-check",
    [Ref("PublicSecurityGroup")],
    False
)

InternalGatewayElb = create_load_balancer(t,
    "IGateway",
    80,
    "/health-check",
    [Ref("PublicSecurityGroup")]
)

InternalMembraneDNSRecord = t.add_resource(route53.RecordSetType(
    "InternalMembraneDNSRecord",
    HostedZoneName=Join("", cell_domain() + ["."]),
    Comment="CNAME redirect to internal membrane elb",
    Name=Join("", ["*", "."] + cell_domain()),
    Type="CNAME",
    TTL="900",
    ResourceRecords=[GetAtt("IGatewayElb", "DNSName")],
    DependsOn=["IGatewayElb", "HostedZone"]
))

WaitHandle = t.add_resource(cfn.WaitConditionHandle("WaitHandle",))

def create_cellos_substack(t, name=None, role=None, cell_modules=None, tags=[],
                           security_groups=[], load_balancers=[],
                           instance_profile=None, instance_type=None,
                           subnet=Ref(private_subnet),
                           associate_public_ip=False):
    params = {
        "Role": role,
        "Tags": tags,
        "CellModules": cell_modules,
        "SecurityGroups": Join(",", security_groups),
        "LoadBalancerNames": Join(",", load_balancers),
        "ZookeeperElb": GetAtt("ZookeeperElb", "DNSName"),
        "MarathonElb": GetAtt("MarathonElb", "DNSName"),
        "MesosElb": GetAtt("MesosElb", "DNSName"),
        "GatewayElb": GetAtt("GatewayElb", "DNSName"),
        "InternalGatewayElb": GetAtt("IGatewayElb", "DNSName"),
        "AssociatePublicIpAddress": "false", # overridden below
        "GroupSize": Ref(name + "Size"),
        "ImageId": FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
        "CellName": Ref("CellName"),
        "BucketName": Ref("BucketName"),
        "Repository": Ref("Repository"),
        "CellOsVersionBundle": Ref("CellOsVersionBundle"),
        "InstanceType": instance_type,
        "Subnet": subnet,
        "KeyName": Ref("KeyName"),
        "SaasBaseSecretAccessKey": Ref("SaasBaseSecretAccessKey"),
        "SaasBaseAccessKeyId": Ref("SaasBaseAccessKeyId"),
        "ParentStackName": Ref("AWS::StackName"),
        "WaitHandle": Ref("WaitHandle"),
    }
    if instance_profile is not None:
        params["IamInstanceProfile"] = Ref(instance_profile)
    if associate_public_ip:
        params["AssociatePublicIpAddress"] = "true"

    substack_template_url = Join("", ["https://s3.amazonaws.com/", Ref("BucketName"), "/", "cell-os--", Ref("CellName"), "/", Ref("BodyStackTemplate")])
    # check if the template url is overridden (e.g. with a release one)
    if options.template_url:
        substack_template_url = options.template_url

    t.add_resource(cfn.Stack(
        name + "Stack",
        TemplateURL=substack_template_url,
        DependsOn="AttachGateway",
        TimeoutInMinutes="10",
        Parameters=params
    ))

# TODO (clehene) cell_modules should come from cluster.yaml (equivalent) mapping of role -> [modules] (CELL-302)

create_cellos_substack(
    t,
    name="Bastion",
    role="bastion",
    cell_modules=modules["bastion"],
    tags="bastion",
    instance_profile="NucleusInstanceProfile",
    security_groups=[
        Ref(BastionSecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    instance_type=Ref(BastionInstanceType),
    subnet=Ref(public_subnet),
    associate_public_ip=True
)

create_cellos_substack(
    t,
    name="Nucleus",
    role="nucleus",
    cell_modules=modules["nucleus"],
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
    cell_modules=modules["membrane"],
    tags="membrane,slave,body",
    instance_profile="MembraneInstanceProfile",
    security_groups=[
        Ref(PublicSecurityGroup),
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("GatewayElb"),
        Ref("IGatewayElb")
    ],
    instance_type=Ref("MembraneInstanceType"),
    subnet=Ref(public_subnet),
    associate_public_ip=True
)

create_cellos_substack(
    t,
    name="StatelessBody",
    role="stateless-body",
    cell_modules=modules["stateless-body"],
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
    cell_modules=modules["stateful-body"],
    tags="slave,body,stateful,stateful-body",
    instance_profile="StatefulBodyInstanceProfile",
    security_groups=[
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    instance_type=Ref("StatefulBodyInstanceType")
)

print(t.to_json(indent=2))
